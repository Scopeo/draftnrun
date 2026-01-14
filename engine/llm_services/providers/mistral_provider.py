import asyncio
import base64
import json
import logging
from typing import Any, Optional

import mistralai
import openai
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from engine.llm_services.constrained_output_models import (
    convert_json_str_to_pydantic,
    format_prompt_with_pydantic_output,
)
from engine.llm_services.providers.base_provider import BaseProvider
from engine.llm_services.utils import validate_and_extract_json_response, wrap_str_content_into_chat_completion_message

LOGGER = logging.getLogger(__name__)


class MistralProvider(BaseProvider):
    def _convert_messages_to_mistral_format(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(messages, list):
            return messages

        mistral_compatible_messages = []
        for message in messages:
            mistral_compatible_message = message.copy()
            role = message.get("role")

            if role != "assistant" and "tool_calls" in mistral_compatible_message:
                del mistral_compatible_message["tool_calls"]

            if role != "tool" and "tool_call_id" in mistral_compatible_message:
                del mistral_compatible_message["tool_call_id"]

            mistral_compatible_message = {k: v for k, v in mistral_compatible_message.items() if v is not None}

            mistral_compatible_messages.append(mistral_compatible_message)

        return mistral_compatible_messages

    def _convert_to_ocr_format(self, messages: list[dict]) -> dict | None:
        if not messages:
            return None

        for message in reversed(messages):
            if not isinstance(message, dict) or "content" not in message:
                continue

            content = message["content"]
            if not content:
                continue

            content_list = content if isinstance(content, list) else [content]

            for content_item in content_list:
                if (
                    isinstance(content_item, dict)
                    and "file" in content_item
                    and isinstance(content_item["file"], dict)
                    and "file_data" in content_item["file"]
                ):
                    return {
                        "type": "document_url",
                        "document_url": content_item["file"]["file_data"],
                    }
                elif (
                    isinstance(content_item, dict)
                    and "image_url" in content_item
                    and isinstance(content_item["image_url"], dict)
                    and "url" in content_item["image_url"]
                ):
                    return {
                        "type": "image_url",
                        "image_url": content_item["image_url"]["url"],
                    }

        return None

    async def complete(
        self,
        messages: list[dict] | str,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[str, int, int, int]:
        if isinstance(messages, list):
            mistral_compatible_messages = self._convert_messages_to_mistral_format(messages)

        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )
        response = await client.chat.completions.create(
            model=self._model_name,
            messages=mistral_compatible_messages,
            temperature=temperature,
        )

        return (
            response.choices[0].message.content,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            response.usage.total_tokens,
        )

    async def embed(self, text: str | list[str], **kwargs) -> tuple[list[float] | list[list[float]], int, int, int]:
        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )
        response = await client.embeddings.create(
            model=self._model_name,
            input=text,
        )

        # Return single embedding or list of embeddings based on input type
        if isinstance(text, str):
            return response.data[0].embedding, response.usage.prompt_tokens, 0, response.usage.total_tokens
        else:
            return (
                [item.embedding for item in response.data],
                response.usage.prompt_tokens,
                0,
                response.usage.total_tokens,
            )

    async def constrained_complete_with_pydantic(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[BaseModel, int, int, int]:
        client = mistralai.Mistral(api_key=self._api_key)

        # Convert messages format if needed
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        response = await client.chat.parse_async(
            model=self._model_name,
            messages=messages,
            temperature=temperature,
            response_format=response_format,
        )

        return (
            response.choices[0].message.parsed,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            response.usage.total_tokens,
        )

    async def constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: dict,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[str, int, int, int]:
        schema = response_format.get("schema", {})
        name = response_format.get("name", "response")

        response_format_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "schema": schema,
            },
        }

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        # Make messages compatible for Mistral API
        mistral_compatible_messages = self._convert_messages_to_mistral_format(messages)

        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )
        response = await client.chat.completions.create(
            model=self._model_name,
            messages=mistral_compatible_messages,
            temperature=temperature,
            stream=stream,
            response_format=response_format_schema,
        )

        # Post-process response to handle models that return schema instead of data
        raw_content = response.choices[0].message.content
        processed_content = validate_and_extract_json_response(raw_content, schema)

        return (
            processed_content,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            response.usage.total_tokens,
        )

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

        # Convert messages to Mistral format
        mistral_messages = self._convert_messages_to_mistral_format(messages)

        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        response = await client.chat.completions.create(
            model=self._model_name,
            messages=mistral_messages,
            tools=tools,
            temperature=temperature,
            stream=stream,
            tool_choice=tool_choice,
        )

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
        raise ValueError("Web search is not supported by Mistral provider. Use OpenAI provider instead.")

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

        # Use Mistral native client for vision
        mclient = mistralai.Mistral(api_key=self._api_key)
        content: list[dict] = [{"type": "text", "text": text_prompt}]
        for img in image_content_list:
            b64 = base64.b64encode(img).decode("utf-8")
            content.append({"type": "image_url", "image_url": f"data:image/png;base64,{b64}"})

        messages = [{"role": "user", "content": content}]

        try:
            mresp = await asyncio.to_thread(
                mclient.chat.complete, model=self._model_name, messages=messages, temperature=temperature
            )

            # Extract token usage if available
            prompt_tokens = getattr(mresp.usage, "prompt_tokens", 0) if hasattr(mresp, "usage") else 0
            completion_tokens = getattr(mresp.usage, "completion_tokens", 0) if hasattr(mresp, "usage") else 0
            total_tokens = getattr(mresp.usage, "total_tokens", 0) if hasattr(mresp, "usage") else 0

            result = mresp.choices[0].message.content

            # If response_format was provided, convert the string response to Pydantic
            if response_format is not None:
                result = convert_json_str_to_pydantic(result, response_format)

            return result, prompt_tokens, completion_tokens, total_tokens

        except Exception as e:
            if "400" in str(e).lower() or "bad request" in str(e).lower():
                raise openai.BadRequestError(f"Mistral vision request failed: {e}", response=None, body=str(e))
            raise

    async def ocr(self, messages: list[dict], **kwargs) -> tuple[str, int, int, int]:
        client = mistralai.Mistral(api_key=self._api_key)

        # Handle case where messages is a dict with "messages" key (from test)
        if isinstance(messages, dict) and "messages" in messages:
            messages = messages["messages"]

        mistral_compatible_messages = self._convert_to_ocr_format(messages)
        if mistral_compatible_messages is None:
            raise ValueError("No OCR compatible messages found")

        ocr_response = await client.ocr.process_async(
            model="mistral-ocr-latest",
            document=mistral_compatible_messages,
            include_image_base64=True,
        )

        # Mistral OCR doesn't provide token usage in the standard format
        return ocr_response.model_dump_json(), 0, 0, 0
