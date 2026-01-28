import base64
import json
import logging
from typing import Optional

import openai
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from engine.llm_services.providers.base_provider import BaseProvider
from engine.llm_services.utils import (
    build_openai_responses_kwargs,
    chat_completion_to_response,
    convert_response_to_chat_completion,
    convert_tools_to_responses_format,
    wrap_str_content_into_chat_completion_message,
)
from settings import settings

LOGGER = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """
    OpenAI provider implementation.

    Handles all OpenAI-specific API calls.
    All methods accept and return data in OpenAI format.
    """

    def __init__(self, api_key: str, base_url: Optional[str], model_name: str, **kwargs):
        self._require_base_url = False  # OpenAI doesn't require base_url
        super().__init__(api_key, base_url, model_name, **kwargs)
        self._verbosity = kwargs.get("verbosity")
        self._reasoning = kwargs.get("reasoning")

    async def complete(
        self,
        messages: list[dict] | str,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[str, int, int, int]:
        messages = chat_completion_to_response(messages)
        client = openai.AsyncOpenAI(api_key=self._api_key)
        kwargs_create = build_openai_responses_kwargs(
            self._model_name,
            self._verbosity,
            self._reasoning,
            temperature,
            {"model": self._model_name, "input": messages, "stream": stream},
        )
        response = await client.responses.create(**kwargs_create)

        return (
            response.output_text,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.usage.total_tokens,
        )

    async def embed(self, text: str | list[str], **kwargs) -> tuple[list[float] | list[list[float]], int, int, int]:
        if self._api_key is None:
            self._api_key = settings.OPENAI_API_KEY

        client = openai.AsyncOpenAI(api_key=self._api_key)
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
        messages = chat_completion_to_response(messages)
        kwargs_create = build_openai_responses_kwargs(
            self._model_name,
            self._verbosity,
            self._reasoning,
            temperature,
            {"input": messages, "model": self._model_name, "stream": stream, "text_format": response_format},
        )

        client = openai.AsyncOpenAI(api_key=self._api_key)
        response = await client.responses.parse(**kwargs_create)

        return (
            response.output_parsed,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.usage.total_tokens,
        )

    def _force_additional_properties_false(self, schema: object) -> None:
        if isinstance(schema, dict):
            if schema.get("type") == "object" and "additionalProperties" not in schema:
                schema["additionalProperties"] = False
            for v in schema.values():
                self._force_additional_properties_false(v)
            return
        if isinstance(schema, list):
            for item in schema:
                self._force_additional_properties_false(item)

    async def constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: dict,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[str, int, int, int]:
        messages = chat_completion_to_response(messages)

        # Extract schema from response_format
        schema = response_format.get("schema", {}) if isinstance(response_format, dict) else {}
        name = response_format.get("name", "response") if isinstance(response_format, dict) else "response"

        # Force additionalProperties to false for OpenAI Responses API
        self._force_additional_properties_false(schema)

        kwargs_create = build_openai_responses_kwargs(
            self._model_name,
            self._verbosity,
            self._reasoning,
            temperature,
            {
                "input": messages,
                "model": self._model_name,
                "stream": stream,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": name,
                        "schema": schema,
                    }
                },
            },
        )

        client = openai.AsyncOpenAI(api_key=self._api_key)
        response = await client.responses.parse(**kwargs_create)

        return (
            response.output_text,
            response.usage.input_tokens,
            response.usage.output_tokens,
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

        messages_for_responses = chat_completion_to_response(messages)
        responses_tools = convert_tools_to_responses_format(tools)

        base_kwargs = {
            "temperature": temperature,
            "model": self._model_name,
            "input": messages_for_responses,
            "tools": responses_tools,
            "stream": stream,
            "tool_choice": tool_choice,
        }

        kwargs_create = build_openai_responses_kwargs(
            self._model_name,
            self._verbosity,
            self._reasoning,
            temperature,
            base_kwargs,
        )

        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        response = await client.responses.create(**kwargs_create)

        chat_completion = convert_response_to_chat_completion(response, self._model_name)

        return (
            chat_completion,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.usage.total_tokens,
        )

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
        tools_with_structured = tools + [structured_output_tool]

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

        messages_for_responses = chat_completion_to_response(messages)
        responses_tools = convert_tools_to_responses_format(tools_with_structured)

        base_kwargs = {
            "temperature": temperature,
            "model": self._model_name,
            "input": messages_for_responses,
            "tools": responses_tools,
            "stream": stream,
            "tool_choice": "required",
        }

        kwargs_create = build_openai_responses_kwargs(
            self._model_name,
            self._verbosity,
            self._reasoning,
            temperature,
            base_kwargs,
        )

        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        response = await client.responses.create(**kwargs_create)

        chat_completion = convert_response_to_chat_completion(response, self._model_name)

        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
        total_tokens = response.usage.total_tokens

        chat_completion = self._filter_and_convert_structured_output_tool(
            response=chat_completion,
            structured_output_tool=structured_output_tool,
        )

        return chat_completion, prompt_tokens, completion_tokens, total_tokens

    async def web_search(
        self, query: str, allowed_domains: Optional[list[str]], **kwargs
    ) -> tuple[str, int, int, int]:
        client = openai.AsyncOpenAI(api_key=self._api_key)
        if allowed_domains:
            tools = [{"type": "web_search", "filters": {"allowed_domains": allowed_domains}}]
        else:
            tools = [{"type": "web_search_preview"}]

        response = await client.responses.create(
            model=self._model_name,
            input=query,
            tools=tools,
        )

        return (
            response.output_text,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.usage.total_tokens,
        )

    async def vision(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel],
        temperature: float,
        **kwargs,
    ) -> tuple[str | BaseModel, int, int, int]:
        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

        # Try OpenAI responses API with file_id uploads for vision (only if no response_format)
        # The responses API doesn't support structured outputs, so skip it when response_format is provided
        file_ids = []
        if response_format is None:
            try:
                responses_input = [{"role": "user", "content": [{"type": "input_text", "text": text_prompt}]}]

                for i, img in enumerate(image_content_list):
                    f = await client.files.create(
                        file=(f"image_{i}.png", img, "image/png"),
                        purpose="vision",
                    )
                    file_ids.append(f.id)
                    responses_input[0]["content"].append({"type": "input_image", "file_id": f.id})

                resp = await client.responses.create(model=self._model_name, input=responses_input)
                prompt_tokens = resp.usage.input_tokens if hasattr(resp.usage, "input_tokens") else 0
                completion_tokens = resp.usage.output_tokens if hasattr(resp.usage, "output_tokens") else 0
                total_tokens = resp.usage.total_tokens if hasattr(resp.usage, "total_tokens") else 0
                return resp.output_text, prompt_tokens, completion_tokens, total_tokens
            except (openai.BadRequestError, openai.UnprocessableEntityError, openai.NotFoundError) as e:
                # Fall back to standard vision API
                LOGGER.warning(
                    f"OpenAI responses API failed ({type(e).__name__}: {str(e)}), falling back to standard vision API"
                )
            finally:
                # Clean up uploaded files
                for file_id in file_ids:
                    try:
                        await client.files.delete(file_id)
                    except Exception:
                        pass

        # Fallback to standard vision with response_format if provided
        content = [{"type": "text", "text": text_prompt}]
        for image_bytes in image_content_list:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

        messages = [{"role": "user", "content": content}]

        if response_format is not None:
            chat_response = await client.beta.chat.completions.parse(
                messages=messages,
                model=self._model_name,
                temperature=temperature,
                response_format=response_format,
            )
            return (
                chat_response.choices[0].message.parsed,
                chat_response.usage.prompt_tokens,
                chat_response.usage.completion_tokens,
                chat_response.usage.total_tokens,
            )
        else:
            chat_response = await client.chat.completions.create(
                messages=messages,
                model=self._model_name,
                temperature=temperature,
            )
            return (
                chat_response.choices[0].message.content,
                chat_response.usage.prompt_tokens,
                chat_response.usage.completion_tokens,
                chat_response.usage.total_tokens,
            )

    async def ocr(self, messages: list[dict], **kwargs) -> tuple[str, int, int, int]:
        raise ValueError("OCR is not specifically supported by OpenAI provider. Use Mistral provider instead.")
