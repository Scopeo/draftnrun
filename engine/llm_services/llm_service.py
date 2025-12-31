import asyncio
import json
import logging
from abc import ABC
from typing import Optional
from uuid import UUID

from openai.types.chat import ChatCompletion
from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel

from engine.agent.types import ToolDescription
from engine.agent.utils import load_str_to_json
from engine.llm_services.constrained_output_models import OutputFormatModel
from engine.llm_services.providers import create_provider
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

DEFAULT_TEMPERATURE = 1


class LLMService(ABC):
    """Base class for all LLM services with provider delegation"""

    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_id: Optional[UUID] = None,
    ):
        self._trace_manager = trace_manager
        self._provider = provider
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._model_id = model_id

    def _set_span_token_counts(self, span, prompt_tokens: int, completion_tokens: Optional[int], total_tokens: int):
        """Set token counts and provider on the current span"""
        attributes = {
            SpanAttributes.LLM_TOKEN_COUNT_PROMPT: prompt_tokens,
            SpanAttributes.LLM_TOKEN_COUNT_TOTAL: total_tokens,
            SpanAttributes.LLM_PROVIDER: self._provider,
        }
        if completion_tokens is not None:
            attributes[SpanAttributes.LLM_TOKEN_COUNT_COMPLETION] = completion_tokens
        span.set_attributes(attributes)


class EmbeddingService(LLMService):
    """Service for text embeddings"""

    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "text-embedding-3-large",
        embedding_size: int = 3072,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url)
        self.embedding_size = embedding_size

        # Create provider instance (factory function handles settings initialization)
        self._provider_instance = create_provider(
            provider=self._provider,
            model_name=self._model_name,
            api_key=self._api_key,
            base_url=self._base_url,
        )
        # Capture the resolved api_key and base_url from the provider instance
        self._api_key = self._provider_instance._api_key
        self._base_url = self._provider_instance._base_url

    def embed_text(self, text: str | list[str]) -> list[float] | list[list[float]]:
        return asyncio.run(self.embed_text_async(text))

    async def embed_text_async(self, text: str | list[str]) -> list[object]:
        """Returns embedding objects with .embedding attribute for qdrant compatibility."""
        span = get_current_span()

        embeddings, prompt_tokens, completion_tokens, total_tokens = await self._provider_instance.embed(text=text)

        self._set_span_token_counts(span, prompt_tokens, None, total_tokens)

        class EmbeddingWrapper:
            def __init__(self, embedding):
                self.embedding = embedding

        if isinstance(embeddings, list) and embeddings:
            if isinstance(embeddings[0], list):
                return [EmbeddingWrapper(emb) for emb in embeddings]
            else:
                return [EmbeddingWrapper(embeddings)]

        return []


class CompletionService(LLMService):
    """Service for text completions with provider delegation"""

    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        verbosity: Optional[str] = None,
        reasoning: Optional[str] = None,
        model_id: Optional[UUID] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url, model_id)
        self._invocation_parameters = {"temperature": temperature}
        if verbosity is not None:
            self._invocation_parameters["verbosity"] = verbosity
        if reasoning is not None:
            self._invocation_parameters["reasoning"] = reasoning

        # Create provider instance (factory function handles settings initialization)
        self._provider_instance = create_provider(
            provider=self._provider,
            model_name=self._model_name,
            api_key=self._api_key,
            base_url=self._base_url,
            **self._invocation_parameters,
        )
        # Capture the resolved api_key and base_url from the provider instance
        self._api_key = self._provider_instance._api_key
        self._base_url = self._provider_instance._base_url

    def _set_span_invocation_parameters(self, span):
        """Set invocation parameters on the current span"""
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps(self._invocation_parameters)})

    def complete(
        self,
        messages: list[dict] | str,
        stream: bool = False,
    ) -> str:
        return asyncio.run(self.complete_async(messages, stream))

    async def complete_async(
        self,
        messages: list[dict] | str,
        stream: bool = False,
    ) -> str:
        span = get_current_span()
        self._set_span_invocation_parameters(span)

        result, prompt_tokens, completion_tokens, total_tokens = await self._provider_instance.complete(
            messages=messages,
            temperature=self._invocation_parameters.get("temperature"),
            stream=stream,
        )

        self._set_span_token_counts(span, prompt_tokens, completion_tokens, total_tokens)

        return result

    def constrained_complete_with_pydantic(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        stream: bool = False,
    ) -> BaseModel:
        return asyncio.run(self.constrained_complete_with_pydantic_async(messages, response_format, stream))

    async def constrained_complete_with_pydantic_async(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        stream: bool = False,
    ) -> BaseModel:
        span = get_current_span()
        self._set_span_invocation_parameters(span)

        (
            result,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        ) = await self._provider_instance.constrained_complete_with_pydantic(
            messages=messages,
            response_format=response_format,
            temperature=self._invocation_parameters.get("temperature"),
            stream=stream,
        )

        self._set_span_token_counts(span, prompt_tokens, completion_tokens, total_tokens)

        return result

    def constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: str,
        stream: bool = False,
    ) -> str:
        return asyncio.run(self.constrained_complete_with_json_schema_async(messages, response_format, stream))

    async def constrained_complete_with_json_schema_async(
        self,
        messages: list[dict] | str,
        response_format: str,
        stream: bool = False,
    ) -> str:
        response_format_dict = load_str_to_json(response_format)
        response_format_dict["strict"] = True
        response_format_dict["type"] = "json_schema"
        response_format_dict = OutputFormatModel(**response_format_dict).model_dump(
            exclude_none=True, exclude_unset=True
        )

        span = get_current_span()
        self._set_span_invocation_parameters(span)

        (
            result,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        ) = await self._provider_instance.constrained_complete_with_json_schema(
            messages=messages,
            response_format=response_format_dict,
            temperature=self._invocation_parameters.get("temperature"),
            stream=stream,
        )

        self._set_span_token_counts(span, prompt_tokens, completion_tokens, total_tokens)

        return result

    def function_call(
        self,
        messages: list[dict] | str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        return asyncio.run(self.function_call_async(messages, stream, tools, tool_choice))

    async def function_call_async(
        self,
        messages: list[dict] | str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
        structured_output_tool: Optional[ToolDescription] = None,
    ) -> ChatCompletion:
        """Main function calling dispatcher"""
        if tools is None:
            tools = []

        # Convert ToolDescription to OpenAI format
        tools_openai = [tool.openai_format for tool in tools]
        structured_openai = structured_output_tool.openai_format if structured_output_tool else None

        span = get_current_span()
        self._set_span_invocation_parameters(span)

        # Delegate to provider based on whether structured output is needed
        if structured_output_tool is not None:
            (
                result,
                prompt_tokens,
                completion_tokens,
                total_tokens,
            ) = await self._provider_instance.function_call_with_structured_output(
                messages=messages,
                tools=tools_openai,
                tool_choice=tool_choice,
                structured_output_tool=structured_openai,
                temperature=self._invocation_parameters.get("temperature"),
                stream=stream,
            )
        else:
            (
                result,
                prompt_tokens,
                completion_tokens,
                total_tokens,
            ) = await self._provider_instance.function_call_without_structured_output(
                messages=messages,
                tools=tools_openai,
                tool_choice=tool_choice,
                temperature=self._invocation_parameters.get("temperature"),
                stream=stream,
            )

        self._set_span_token_counts(span, prompt_tokens, completion_tokens, total_tokens)

        return result


class WebSearchService(LLMService):
    """Service for web search"""

    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_id: Optional[UUID] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url, model_id)

        # Create provider instance (factory function handles settings initialization)
        self._provider_instance = create_provider(
            provider=self._provider,
            model_name=self._model_name,
            api_key=self._api_key,
            base_url=self._base_url,
        )
        # Capture the resolved api_key and base_url from the provider instance
        self._api_key = self._provider_instance._api_key
        self._base_url = self._provider_instance._base_url

    def web_search(self, query: str, allowed_domains: Optional[list[str]] = None) -> str:
        return asyncio.run(self.web_search_async(query, allowed_domains))

    async def web_search_async(self, query: str, allowed_domains: Optional[list[str]] = None) -> str:
        span = get_current_span()

        result, prompt_tokens, completion_tokens, total_tokens = await self._provider_instance.web_search(
            query=query,
            allowed_domains=allowed_domains,
        )

        self._set_span_token_counts(span, prompt_tokens, completion_tokens, total_tokens)

        return result


class VisionService(LLMService):
    """Service for vision/image processing"""

    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url)
        self._temperature = temperature

        # Create provider instance (factory function handles settings initialization)
        self._provider_instance = create_provider(
            provider=self._provider,
            model_name=self._model_name,
            api_key=self._api_key,
            base_url=self._base_url,
        )

        # Store initialized values from provider
        self._api_key = self._provider_instance._api_key
        self._base_url = self._provider_instance._base_url

    def _set_span_invocation_parameters(self, span):
        """Set invocation parameters on the current span"""
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})

    def get_image_description(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel] = None,
    ) -> str | BaseModel:
        return asyncio.run(self.get_image_description_async(image_content_list, text_prompt, response_format))

    async def get_image_description_async(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel] = None,
    ) -> str | BaseModel:
        span = get_current_span()
        self._set_span_invocation_parameters(span)

        result, prompt_tokens, completion_tokens, total_tokens = await self._provider_instance.vision(
            image_content_list=image_content_list,
            text_prompt=text_prompt,
            response_format=response_format,
            temperature=self._temperature,
        )

        self._set_span_token_counts(span, prompt_tokens, completion_tokens, total_tokens)

        return result


class OCRService(LLMService):
    """Service for OCR processing"""

    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "mistral",
        model_name: str = "mistral-ocr-latest",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_id: Optional[UUID] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url, model_id)

        # Create provider instance (factory function handles settings initialization)
        self._provider_instance = create_provider(
            provider=self._provider,
            model_name=self._model_name,
            api_key=self._api_key,
            base_url=self._base_url,
        )

        # Store initialized values from provider
        self._api_key = self._provider_instance._api_key
        self._base_url = self._provider_instance._base_url

    def get_ocr_text(self, messages: list[dict]) -> str:
        return asyncio.run(self.get_ocr_text_async(messages))

    async def get_ocr_text_async(self, messages: list[dict]) -> str:
        # Delegate to provider
        result, prompt_tokens, completion_tokens, total_tokens = await self._provider_instance.ocr(messages=messages)

        return result
