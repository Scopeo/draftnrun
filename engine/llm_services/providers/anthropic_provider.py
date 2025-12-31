import base64
import json
import logging
import time
from typing import Optional

import httpx
import openai
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function
from openai.types.completion_usage import CompletionUsage
from pydantic import BaseModel

from engine.agent.utils import load_str_to_json
from engine.llm_services.constrained_output_models import (
    convert_json_str_to_pydantic,
    format_prompt_with_pydantic_output,
)
from engine.llm_services.providers.base_provider import BaseProvider
from engine.llm_services.utils import wrap_str_content_into_chat_completion_message

LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS_ANTHROPIC = 4096


def _force_additional_properties_false_for_object_schemas(schema: object) -> None:
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "additionalProperties" not in schema:
            schema["additionalProperties"] = False
        for v in schema.values():
            _force_additional_properties_false_for_object_schemas(v)
        return
    if isinstance(schema, list):
        for item in schema:
            _force_additional_properties_false_for_object_schemas(item)


class AnthropicProvider(BaseProvider):
    def _build_anthropic_text_messages(self, messages: list[dict] | str) -> tuple[list[dict], str | None]:
        if isinstance(messages, str):
            return [{"role": "user", "content": [{"type": "text", "text": messages}]}], None

        system_messages = []
        anthropic_messages: list[dict] = []
        pending_tool_results: list[dict] = []

        def flush_pending_tool_results():
            if pending_tool_results:
                anthropic_messages.append({"role": "user", "content": pending_tool_results.copy()})
                pending_tool_results.clear()

        for m in messages:
            role = m.get("role")
            content = m.get("content")

            if role == "system":
                flush_pending_tool_results()
                if isinstance(content, str):
                    system_messages.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            system_messages.append(item.get("text", ""))
            elif role == "tool":
                tool_call_id = m.get("tool_call_id")
                tool_result_content = content if isinstance(content, str) else ""
                pending_tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": tool_result_content,
                })
            elif role == "assistant" and m.get("tool_calls"):
                flush_pending_tool_results()
                tool_calls = m.get("tool_calls", [])
                anthropic_content = []

                if content and isinstance(content, str):
                    anthropic_content.append({"type": "text", "text": content})

                for tc in tool_calls:
                    tool_use_block = {
                        "type": "tool_use",
                        "id": tc.get("id"),
                        "name": tc.get("function", {}).get("name"),
                        "input": load_str_to_json(tc.get("function", {}).get("arguments", "{}")),
                    }
                    anthropic_content.append(tool_use_block)

                anthropic_messages.append({"role": "assistant", "content": anthropic_content})
            else:
                flush_pending_tool_results()
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                elif isinstance(content, list):
                    converted_content = []
                    for item in content:
                        if not isinstance(item, dict):
                            converted_content.append(item)
                            continue

                        item_type = item.get("type")
                        if item_type == "image_url":
                            image_url_data = item.get("image_url", {})
                            url = image_url_data.get("url", "") if isinstance(image_url_data, dict) else image_url_data

                            if url.startswith("data:"):
                                try:
                                    header, data = url.split(",", 1)
                                    media_type = header.split(";")[0].replace("data:", "")
                                    converted_content.append({
                                        "type": "image",
                                        "source": {"type": "base64", "media_type": media_type, "data": data},
                                    })
                                except (ValueError, IndexError):
                                    LOGGER.warning(f"Failed to parse data URL for image: {url[:100]}")
                            elif url.startswith(("http://", "https://")):
                                converted_content.append({"type": "image", "source": {"type": "url", "url": url}})
                            else:
                                LOGGER.warning(f"Unsupported image URL format for Anthropic: {url[:100]}")
                        else:
                            converted_content.append(item)
                    content = converted_content
                anthropic_messages.append({"role": role, "content": content})

        flush_pending_tool_results()

        system_prompt = "\n\n".join(system_messages) if system_messages else None

        return anthropic_messages, system_prompt

    def _convert_response_to_openai(self, anthropic_response: dict) -> ChatCompletion:
        tool_calls = []
        text_content = ""

        for idx, content_block in enumerate(anthropic_response.get("content", [])):
            if content_block.get("type") == "tool_use":
                tool_calls.append(
                    ChatCompletionMessageToolCall(
                        id=content_block.get("id", f"call_{idx}"),
                        type="function",
                        function=Function(
                            name=content_block.get("name", ""),
                            arguments=json.dumps(content_block.get("input", {})),
                        ),
                    )
                )
            elif content_block.get("type") == "text":
                text_content += content_block.get("text", "")

        message = ChatCompletionMessage(
            role="assistant",
            content=text_content if text_content else None,
            tool_calls=tool_calls if tool_calls else None,
        )

        usage = CompletionUsage(
            prompt_tokens=anthropic_response.get("usage", {}).get("input_tokens", 0),
            completion_tokens=anthropic_response.get("usage", {}).get("output_tokens", 0),
            total_tokens=anthropic_response.get("usage", {}).get("input_tokens", 0)
            + anthropic_response.get("usage", {}).get("output_tokens", 0),
        )

        anthropic_stop_reason = anthropic_response.get("stop_reason", "stop")
        finish_reason_map = {
            "end_turn": "stop",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "tool_use": "tool_calls",
        }
        finish_reason = finish_reason_map.get(anthropic_stop_reason, "stop")

        return ChatCompletion(
            id=anthropic_response.get("id", f"chatcmpl-{int(time.time())}"),
            object="chat.completion",
            created=int(time.time()),
            model=anthropic_response.get("model", self._model_name),
            choices=[
                Choice(
                    index=0,
                    message=message,
                    finish_reason=finish_reason,
                )
            ],
            usage=usage,
        )

    def _convert_tool_to_anthropic(self, tool: dict) -> dict:
        return {
            "name": tool["function"]["name"],
            "description": tool["function"]["description"],
            "input_schema": tool["function"]["parameters"],
        }

    async def complete(
        self,
        messages: list[dict] | str,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[str, int, int, int]:
        endpoint = str(self._base_url).rstrip("/")
        headers = {"x-api-key": str(self._api_key), "anthropic-version": "2023-06-01"}
        anthropic_messages, system_prompt = self._build_anthropic_text_messages(messages)
        body = {
            "model": self._model_name,
            "max_tokens": DEFAULT_MAX_TOKENS_ANTHROPIC,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=30) as h:
                r = await h.post(endpoint, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as e:
            raise ValueError(f"Anthropic completion request failed: {type(e).__name__}: {e}") from e

        if r.status_code >= 400:
            if r.status_code == 400:
                raise openai.BadRequestError(
                    f"Anthropic completion request failed status_code={r.status_code}: {r.text[:300]}",
                    response=r,
                    body=r.text,
                )
            raise ValueError(f"Anthropic completion request failed with status_code={r.status_code}: {r.text[:300]}")

        try:
            data = r.json()
        except json.JSONDecodeError as e:
            raise ValueError(f"Anthropic completion response was not JSON: {type(e).__name__}: {e}") from e

        content_items = data.get("content")
        if not isinstance(content_items, list) or not content_items:
            raise ValueError("Anthropic completion response is missing 'content' list")

        text = None
        for item in content_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "text":
                continue
            item_text = item.get("text")
            if isinstance(item_text, str) and item_text:
                text = item_text
                break

        if not isinstance(text, str) or not text:
            raise ValueError("Anthropic completion response is missing any text content blocks")

        usage_dict = data.get("usage", {})
        input_tokens = usage_dict.get("input_tokens", 0)
        output_tokens = usage_dict.get("output_tokens", 0)
        total_tokens = (
            input_tokens + output_tokens if isinstance(input_tokens, int) and isinstance(output_tokens, int) else 0
        )

        return text, input_tokens, output_tokens, total_tokens

    async def embed(self, text: str | list[str], **kwargs) -> tuple[list[float] | list[list[float]], int, int, int]:
        raise ValueError("Embeddings are not supported by Anthropic provider. Use OpenAI provider instead.")

    async def constrained_complete_with_pydantic(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[BaseModel, int, int, int]:
        schema = response_format.model_json_schema()
        _force_additional_properties_false_for_object_schemas(schema)

        endpoint = str(self._base_url).rstrip("/")
        headers = {
            "x-api-key": str(self._api_key),
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "structured-outputs-2025-11-13",
        }

        anthropic_messages, system_prompt = self._build_anthropic_text_messages(messages)
        body = {
            "model": self._model_name,
            "max_tokens": DEFAULT_MAX_TOKENS_ANTHROPIC,
            "temperature": temperature,
            "messages": anthropic_messages,
            "output_format": {"type": "json_schema", "schema": schema},
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=120) as h:
                r = await h.post(endpoint, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as e:
            raise ValueError(f"Anthropic structured output request failed: {type(e).__name__}: {e}") from e

        if r.status_code >= 400:
            if r.status_code == 400:
                raise openai.BadRequestError(
                    f"Anthropic structured output request failed status_code={r.status_code}: {r.text[:300]}",
                    response=r,
                    body=r.text,
                )
            raise ValueError(
                f"Anthropic structured output request failed with status_code={r.status_code}: {r.text[:300]}"
            )

        data = r.json()
        content_items = data.get("content")
        if not isinstance(content_items, list) or not content_items:
            raise ValueError(
                "Anthropic structured output response is missing 'content' list; "
                f"provider=anthropic model={self._model_name}"
            )

        text = content_items[0].get("text") if isinstance(content_items[0], dict) else None
        if not isinstance(text, str) or not text:
            raise ValueError(
                "Anthropic structured output response is missing content[0].text; "
                f"provider=anthropic model={self._model_name}"
            )

        parsed = load_str_to_json(text)
        answer = response_format(**parsed)

        usage_dict = data.get("usage", {})
        input_tokens = usage_dict.get("input_tokens", 0)
        output_tokens = usage_dict.get("output_tokens", 0)
        total_tokens = (
            input_tokens + output_tokens if isinstance(input_tokens, int) and isinstance(output_tokens, int) else 0
        )

        return answer, input_tokens, output_tokens, total_tokens

    async def constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: dict,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[str, int, int, int]:
        schema = response_format.get("schema", {}) if isinstance(response_format, dict) else {}
        _force_additional_properties_false_for_object_schemas(schema)

        endpoint = str(self._base_url).rstrip("/")
        headers = {
            "x-api-key": str(self._api_key),
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "structured-outputs-2025-11-13",
        }

        anthropic_messages, system_prompt = self._build_anthropic_text_messages(messages)
        body = {
            "model": self._model_name,
            "max_tokens": DEFAULT_MAX_TOKENS_ANTHROPIC,
            "temperature": temperature,
            "messages": anthropic_messages,
            "output_format": {"type": "json_schema", "schema": schema},
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=120) as h:
                r = await h.post(endpoint, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as e:
            raise ValueError(f"Anthropic structured output request failed: {type(e).__name__}: {e}") from e

        if r.status_code >= 400:
            raise ValueError(
                f"Anthropic structured output request failed with status_code={r.status_code}: {r.text[:300]}"
            )

        data = r.json()
        content_items = data.get("content")
        if not isinstance(content_items, list) or not content_items:
            raise ValueError(
                "Anthropic structured output response is missing 'content' list; "
                f"provider=anthropic model={self._model_name}"
            )

        text = content_items[0].get("text") if isinstance(content_items[0], dict) else None
        if not isinstance(text, str) or not text:
            raise ValueError(
                "Anthropic structured output response is missing content[0].text; "
                f"provider=anthropic model={self._model_name}"
            )

        parsed = load_str_to_json(text)

        usage_dict = data.get("usage", {})
        input_tokens = usage_dict.get("input_tokens", 0)
        output_tokens = usage_dict.get("output_tokens", 0)
        total_tokens = (
            input_tokens + output_tokens if isinstance(input_tokens, int) and isinstance(output_tokens, int) else 0
        )

        return json.dumps(parsed, ensure_ascii=False), input_tokens, output_tokens, total_tokens

    async def function_call_without_structured_output(
        self,
        messages: list[dict] | str,
        tools: list[dict],
        tool_choice: str,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[ChatCompletion, int, int, int]:
        if len(tools) == 0 or tool_choice == "none":
            LOGGER.info("Making simple completion call without tools")
            content, prompt_tokens, completion_tokens, total_tokens = await self.complete(
                messages=messages,
                temperature=temperature,
                stream=stream,
            )
            response = wrap_str_content_into_chat_completion_message(content, self._model_name)
            return response, prompt_tokens, completion_tokens, total_tokens

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        anthropic_messages, system_prompt = self._build_anthropic_text_messages(messages)

        tools_anthropic = [self._convert_tool_to_anthropic(tool) for tool in tools] if tools else []

        anthropic_tool_choice = None
        if tools_anthropic:
            if tool_choice == "required":
                anthropic_tool_choice = {"type": "any"}
            elif tool_choice == "auto":
                anthropic_tool_choice = {"type": "auto"}
            elif tool_choice and tool_choice not in ["none", "auto", "required"]:
                anthropic_tool_choice = {"type": "tool", "name": tool_choice}

        endpoint = str(self._base_url).rstrip("/")
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        body = {
            "model": self._model_name,
            "messages": anthropic_messages,
            "max_tokens": DEFAULT_MAX_TOKENS_ANTHROPIC,
            "temperature": temperature,
        }

        if system_prompt:
            body["system"] = system_prompt

        if tools_anthropic:
            body["tools"] = tools_anthropic
            if anthropic_tool_choice:
                body["tool_choice"] = anthropic_tool_choice

        try:
            async with httpx.AsyncClient(timeout=30) as h:
                r = await h.post(endpoint, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as e:
            raise ValueError(f"Anthropic function call request failed: {type(e).__name__}: {e}") from e

        if r.status_code >= 400:
            raise openai.BadRequestError(
                f"Anthropic function call failed status_code={r.status_code}: {r.text[:300]}",
                response=r,
                body=r.text,
            )

        anthropic_response = r.json()

        response = self._convert_response_to_openai(anthropic_response)

        return response, response.usage.prompt_tokens, response.usage.completion_tokens, response.usage.total_tokens

    async def function_call_with_structured_output(
        self,
        messages: list[dict] | str,
        tools: list[dict],
        tool_choice: str,
        structured_output_tool: dict,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[ChatCompletion, int, int, int]:
        if len(tools) == 0 or tool_choice == "none":
            LOGGER.info("Getting structured response without tools using LLM constrained method")

            structured_json_output = json.dumps({
                "name": structured_output_tool["function"]["name"],
                "schema": structured_output_tool["function"]["parameters"],
            })

            (
                structured_content,
                prompt_tokens,
                completion_tokens,
                total_tokens,
            ) = await self.constrained_complete_with_json_schema(
                messages=messages,
                response_format=json.loads(structured_json_output),
                temperature=temperature,
                stream=stream,
            )
            response = wrap_str_content_into_chat_completion_message(structured_content, self._model_name)
            return response, prompt_tokens, completion_tokens, total_tokens

        tools_with_structured = tools + [structured_output_tool]
        response, prompt_tokens, completion_tokens, total_tokens = await self.function_call_without_structured_output(
            messages=messages,
            tools=tools_with_structured,
            tool_choice="required",
            temperature=temperature,
            stream=stream,
        )

        response = self._filter_and_convert_structured_output_tool(
            response=response,
            structured_output_tool=structured_output_tool,
        )

        return response, prompt_tokens, completion_tokens, total_tokens

    async def web_search(
        self, query: str, allowed_domains: Optional[list[str]], **kwargs
    ) -> tuple[str, int, int, int]:
        raise ValueError("Web search is not supported by Anthropic provider. Use OpenAI provider instead.")

    async def vision(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel],
        temperature: float,
        **kwargs,
    ) -> tuple[str | BaseModel, int, int, int]:
        if response_format is not None:
            text_prompt = format_prompt_with_pydantic_output(text_prompt, response_format)

        endpoint = str(self._base_url).rstrip("/")
        headers = {"x-api-key": str(self._api_key), "anthropic-version": "2023-06-01"}

        # Build content with text prompt followed by all images
        content = [{"type": "text", "text": text_prompt}]
        for img in image_content_list:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(img).decode("utf-8"),
                },
            })

        body = {
            "model": self._model_name,
            "max_tokens": DEFAULT_MAX_TOKENS_ANTHROPIC,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as h:
                r = await h.post(endpoint, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as e:
            raise ValueError(f"Anthropic vision request failed: {type(e).__name__}: {e}") from e

        if r.status_code >= 400:
            if r.status_code == 400:
                raise openai.BadRequestError(
                    f"Anthropic vision request failed status_code={r.status_code}: {r.text[:300]}",
                    response=r,
                    body=r.text,
                )
            if r.status_code in {429, 500, 502, 503, 504, 529}:
                raise ValueError(
                    f"Anthropic vision request failed with temporary provider-side error "
                    f"status_code={r.status_code}: {r.text[:300]}"
                )
            raise ValueError(f"Anthropic vision request failed with status_code={r.status_code}: {r.text[:300]}")

        data = r.json()
        content_items = data.get("content")
        if isinstance(content_items, list) and content_items:
            item0 = content_items[0]
            if isinstance(item0, dict) and isinstance(item0.get("text"), str):
                result = item0["text"]
            else:
                result = str(data)
        else:
            result = str(data)

        if response_format is not None:
            if not result or not isinstance(result, str):
                raise ValueError(f"Anthropic API returned empty or invalid response for structured output: {result}")
            result = convert_json_str_to_pydantic(result, response_format)

        usage_dict = data.get("usage", {})
        prompt_tokens = usage_dict.get("input_tokens", 0)
        completion_tokens = usage_dict.get("output_tokens", 0)
        total_tokens = prompt_tokens + completion_tokens

        return result, prompt_tokens, completion_tokens, total_tokens

    async def ocr(self, messages: list[dict], **kwargs) -> tuple[str, int, int, int]:
        raise ValueError("OCR is not specifically supported by Anthropic provider. Use Mistral provider instead.")
