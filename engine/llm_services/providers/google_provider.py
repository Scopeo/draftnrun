import asyncio
import json
import logging
from typing import Optional

import openai
from google import genai
from google.genai import errors as google_genai_errors
from google.genai import types as google_genai_types
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from engine.llm_services.constrained_output_models import convert_json_str_to_pydantic
from engine.llm_services.providers.base_provider import BaseProvider
from engine.llm_services.utils import validate_and_extract_json_response, wrap_str_content_into_chat_completion_message

LOGGER = logging.getLogger(__name__)


class GoogleProvider(BaseProvider):
    async def complete(
        self,
        messages: list[dict] | str,
        temperature: float,
        stream: bool,
        **kwargs,
    ) -> tuple[str, int, int, int]:
        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )
        response = await client.chat.completions.create(
            model=self._model_name,
            messages=messages,
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
        (
            result,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        ) = await self._fallback_constrained_complete_with_json_format(
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            stream=stream,
        )
        return result, prompt_tokens, completion_tokens, total_tokens

    async def _fallback_constrained_complete_with_json_format(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        temperature: float,
        stream: bool,
    ) -> tuple[BaseModel, int, int, int]:
        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

        response_format_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": response_format.__name__,
                "schema": response_format.model_json_schema(),
                "strict": True,
            },
        }

        schema = response_format_schema.get("json_schema", {}).get("schema", {})
        self._force_additional_properties_false(schema)

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        response = await client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            temperature=temperature,
            stream=stream,
            response_format=response_format_schema,
        )

        response_dict = json.loads(response.choices[0].message.content)
        return (
            response_format(**response_dict),
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
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
        schema = response_format.get("schema", {})
        name = response_format.get("name", "response")

        response_format_schema = {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "schema": schema,
                "strict": True,
            },
        }

        self._force_additional_properties_false(schema)

        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )
        response = await client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            temperature=temperature,
            stream=stream,
            response_format=response_format_schema,
        )

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

        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        response = await client.chat.completions.create(
            model=self._model_name,
            messages=messages,
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
        raise ValueError("Web search is not supported by Google provider. Use OpenAI provider instead.")

    async def vision(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel],
        temperature: float,
        **kwargs,
    ) -> tuple[str | BaseModel, int, int, int]:
        try:
            from engine.llm_services.constrained_output_models import format_prompt_with_pydantic_output

            gclient = genai.Client(api_key=self._api_key)

            # If response_format is provided, format the prompt to request JSON output
            if response_format is not None:
                formatted_prompt = format_prompt_with_pydantic_output(text_prompt, response_format)
            else:
                formatted_prompt = text_prompt

            parts: list = [google_genai_types.Part.from_text(text=formatted_prompt)]
            for img in image_content_list:
                parts.append(google_genai_types.Part.from_bytes(data=img, mime_type="image/png"))

            config = google_genai_types.GenerateContentConfig(temperature=temperature)
            resp = await asyncio.to_thread(
                gclient.models.generate_content, model=self._model_name, contents=parts, config=config
            )
            result_text = getattr(resp, "text", None)

            # Handle None or empty text response
            if result_text is None or (isinstance(result_text, str) and not result_text.strip()):
                # Try to get text from string representation
                result_text = str(resp) if resp else ""

            result = result_text

            # If response_format was provided, convert the string response to Pydantic
            if response_format is not None:
                if not result or not isinstance(result, str):
                    raise ValueError(f"Google API returned empty or invalid response for structured output: {result}")
                result = convert_json_str_to_pydantic(result, response_format)

            # Google doesn't provide token usage in the standard format
            return result, 0, 0, 0

        except (
            google_genai_errors.APIError,
            google_genai_errors.ClientError,
            google_genai_errors.ServerError,
            ValueError,
            TypeError,
        ) as e:
            raise ValueError(f"Google vision request failed: {e}") from e

    async def ocr(self, messages: list[dict], **kwargs) -> tuple[str, int, int, int]:
        raise ValueError("OCR is not specifically supported by Google provider. Use Mistral provider instead.")
