import json
import logging
from functools import wraps
from typing import Optional
from abc import ABC
from pydantic import BaseModel

from opentelemetry.trace import get_current_span
from openinference.semconv.trace import SpanAttributes

from engine.llm_services.utils import (
    check_usage,
    make_messages_compatible_for_mistral,
    make_mistral_ocr_compatible,
)
from engine.trace.trace_manager import TraceManager
from engine.agent.data_structures import ToolDescription
from engine.agent.utils import load_str_to_json
from engine.llm_services.constrained_output_models import OutputFormatModel
from settings import settings
from engine.llm_services.utils import chat_completion_to_response
from openai.types.chat import ChatCompletion

LOGGER = logging.getLogger(__name__)


def with_usage_check(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        provider = getattr(self, "_provider", None)
        if provider is None:
            raise ValueError("Instance must have a 'provider' attribute to perform usage check.")

        check_usage(provider)
        return func(self, *args, **kwargs)

    return wrapper


def with_async_usage_check(func):
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        provider = getattr(self, "_provider", None)
        if provider is None:
            raise ValueError("Instance must have a 'provider' attribute to perform usage check.")

        check_usage(provider)
        return await func(self, *args, **kwargs)

    return wrapper


class LLMService(ABC):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self._trace_manager = trace_manager
        self._provider = provider
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        if self._api_key is None or self._base_url is None:
            match self._provider:
                case "openai":
                    self._api_key = settings.OPENAI_API_KEY
                    self._base_url = None
                case "cerebras":
                    self._api_key = settings.CEREBRAS_API_KEY
                    self._base_url = settings.CEREBRAS_BASE_URL
                case "google":
                    self._api_key = settings.GOOGLE_API_KEY
                    self._base_url = settings.GOOGLE_BASE_URL
                case "mistral":
                    self._api_key = settings.MISTRAL_API_KEY
                    self._base_url = settings.MISTRAL_BASE_URL
                case _:
                    self._api_key = settings.custom_models.get(self._provider).get("api_key")
                    self._base_url = settings.custom_models.get(self._provider).get("base_url")
                    LOGGER.debug(f"Using custom api key and base url for provider: {self._provider}")


class EmbeddingService(LLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "text-embedding-3-large",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url)

    def embed_text(self, text: str) -> list[float]:
        span = get_current_span()
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=self._api_key)
                response = client.embeddings.create(
                    model=self._model_name,
                    input=text,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.data

            case _:
                import openai

                client = openai.OpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = client.embeddings.create(
                    model=self._model_name,
                    input=text,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.data

    async def embed_text_async(self, text: str) -> list[float]:
        span = get_current_span()
        match self._provider:
            case "openai":
                import openai

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY

                client = openai.AsyncOpenAI(api_key=self._api_key)
                response = await client.embeddings.create(
                    model=self._model_name,
                    input=text,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.data

            case _:
                import openai

                client = openai.AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = await client.embeddings.create(
                    model=self._model_name,
                    input=text,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.data


class CompletionService(LLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.5,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url)
        self._temperature = temperature

    @with_usage_check
    def complete(
        self,
        messages: list[dict] | str,
        stream: bool = False,
    ) -> str:
        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai":
                import openai

                messages = chat_completion_to_response(messages)
                client = openai.OpenAI(api_key=self._api_key)
                response = client.responses.create(
                    model=self._model_name,
                    input=messages,
                    temperature=self._temperature,
                    stream=stream,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_text

            case _:  # all the providers that are using openai chat completion go here
                import openai

                client = openai.OpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                    stream=stream,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.choices[0].message.content

    @with_async_usage_check
    async def complete_async(
        self,
        messages: list[dict] | str,
        stream: bool = False,
    ) -> str:
        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai":
                import openai

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY
                messages = chat_completion_to_response(messages)
                client = openai.AsyncOpenAI(api_key=self._api_key)
                response = await client.responses.create(
                    model=self._model_name,
                    input=messages,
                    temperature=self._temperature,
                    stream=stream,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_text

            case _:
                import openai

                client = openai.AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = await client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.choices[0].message.content

    @with_usage_check
    def constrained_complete_with_pydantic(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        stream: bool = False,
    ) -> BaseModel:
        kwargs = {
            "input": messages,
            "model": self._model_name,
            "temperature": self._temperature,
            "stream": stream,
        }

        kwargs["text_format"] = response_format

        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=self._api_key)
                messages = chat_completion_to_response(messages)
                response = client.responses.parse(**kwargs)
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_parsed
            case "cerebras" | "google":  # all providers using only json schema for structured output go here
                import openai

                client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)

                response_format_schema = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_format.__name__,
                        "schema": response_format.model_json_schema(),
                        "strict": True,
                    },
                }
                if isinstance(messages, str):
                    messages = [{"role": "user", "content": messages}]

                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                    stream=stream,
                    response_format=response_format_schema,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                response_dict = json.loads(response.choices[0].message.content)
                return response_format(**response_dict)

            case "mistral":
                import mistralai

                client = mistralai.Mistral(api_key=self._api_key)
                if isinstance(messages, str):
                    messages = [{"role": "user", "content": messages}]
                response = client.chat.parse(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                    response_format=response_format,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.choices[0].message.parsed

            case _:
                raise ValueError(f"Invalid provider for constrained complete with pydantic: {self._provider}")

    @with_async_usage_check
    async def constrained_complete_with_pydantic_async(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> BaseModel:
        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai":
                import openai

                # Transform messages for OpenAI response API
                messages = chat_completion_to_response(messages)
                kwargs = {
                    "input": messages,
                    "model": self._model_name,
                    "temperature": self._temperature,
                    "stream": stream,
                    "text_format": response_format,
                }

                client = openai.AsyncOpenAI(api_key=self._api_key)
                response = await client.responses.parse(**kwargs)
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_parsed

            case "cerebras" | "google":  # all providers using only json schema for structured output go here
                import openai

                client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

                response_format_schema = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_format.__name__,
                        "schema": response_format.model_json_schema(),
                        "strict": True,
                    },
                }
                if isinstance(messages, str):
                    messages = [{"role": "user", "content": messages}]

                response = await client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                    stream=stream,
                    response_format=response_format_schema,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                response_dict = json.loads(response.choices[0].message.content)
                return response_format(**response_dict)
            case "mistral":
                import mistralai

                client = mistralai.Mistral(api_key=self._api_key)
                # Convert messages format if needed
                if isinstance(messages, str):
                    messages = [{"role": "user", "content": messages}]
                response = client.chat.parse(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                    response_format=response_format,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.choices[0].message.parsed

            case _:
                raise ValueError(f"Invalid provider: {self._provider}")

    @with_usage_check
    def constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: str,
        stream: bool = False,
    ) -> str:
        kwargs = {
            "input": messages,
            "model": self._model_name,
            "temperature": self._temperature,
            "stream": stream,
        }
        response_format = load_str_to_json(response_format)
        # validate with the basemodel OutputFormatModel
        response_format["strict"] = True
        response_format["type"] = "json_schema"
        response_format = OutputFormatModel(**response_format).model_dump(exclude_none=True, exclude_unset=True)
        kwargs["text"] = {"format": response_format}

        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=self._api_key)
                messages = chat_completion_to_response(messages)
                response = client.responses.parse(**kwargs)
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_text
            case "cerebras" | "google" | "mistral":  # all the providers that are using openai chat completion go here
                import openai

                schema = response_format.get("schema", {})
                name = response_format.get("name", "response")

                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": name,
                        "schema": schema,
                    },
                }

                client = openai.OpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                    stream=stream,
                    response_format=response_format,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.choices[0].message.content
            case _:
                raise ValueError(f"Invalid provider for constrained complete with json schema: {self._provider}")

    @with_async_usage_check
    async def constrained_complete_with_json_schema_async(
        self,
        messages: list[dict] | str,
        response_format: str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> str:
        response_format = load_str_to_json(response_format)
        # validate with the basemodel OutputFormatModel
        response_format["strict"] = True
        response_format["type"] = "json_schema"
        response_format = OutputFormatModel(**response_format).model_dump(exclude_none=True, exclude_unset=True)

        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai":
                import openai

                # Transform messages for OpenAI response API
                messages = chat_completion_to_response(messages)
                kwargs = {
                    "input": messages,
                    "model": self._model_name,
                    "temperature": self._temperature,
                    "stream": stream,
                    "text": {"format": response_format},
                }

                client = openai.AsyncOpenAI(api_key=self._api_key)
                response = await client.responses.parse(**kwargs)
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_text
            case "cerebras" | "google" | "mistral":  # all the providers that are using openai chat completion go here
                import openai

                schema = response_format.get("schema", {})
                name = response_format.get("name", "response")

                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": name,
                        "schema": schema,
                    },
                }

                if isinstance(messages, str):
                    messages = [{"role": "user", "content": messages}]

                client = openai.AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = await client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                    stream=stream,
                    response_format=response_format,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.choices[0].message.content
            case _:
                raise ValueError(f"Invalid provider for constrained complete with json schema: {self._provider}")

    @with_usage_check
    def function_call(
        self,
        messages: list[dict] | str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        if tools is None:
            tools = []

        openai_tools = [tool.openai_format for tool in tools]

        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai" | "google":
                import openai

                client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    tools=openai_tools,
                    temperature=self._temperature,
                    stream=stream,
                    tool_choice=tool_choice,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response
            case "mistral":
                import openai

                mistral_compatible_messages = make_messages_compatible_for_mistral(messages)

                client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=mistral_compatible_messages,
                    tools=openai_tools,
                    temperature=self._temperature,
                    stream=stream,
                    tool_choice=tool_choice,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response
            case _:  # all the providers that are using openai chat completion go here
                import openai

                client = openai.OpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    tools=openai_tools,
                    temperature=self._temperature,
                    stream=stream,
                    tool_choice=tool_choice,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response

    @with_async_usage_check
    async def function_call_async(
        self,
        messages: list[dict] | str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        if tools is None:
            tools = []

        openai_tools = [tool.openai_format for tool in tools]

        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai" | "google":
                import openai

                client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
                response = await client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    tools=openai_tools,
                    temperature=self._temperature,
                    stream=stream,
                    tool_choice=tool_choice,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response
            case "mistral":
                import openai

                mistral_compatible_messages = make_messages_compatible_for_mistral(messages)

                client = openai.AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = await client.chat.completions.create(
                    model=self._model_name,
                    messages=mistral_compatible_messages,
                    tools=openai_tools,
                    temperature=self._temperature,
                    stream=stream,
                    tool_choice=tool_choice,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response
            case _:
                import openai

                client = openai.AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = await client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    tools=openai_tools,
                    temperature=self._temperature,
                    stream=stream,
                    tool_choice=tool_choice,
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response


class WebSearchService(LLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url)

    @with_usage_check
    def web_search(self, query: str) -> str:
        span = get_current_span()
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=self._api_key)
                response = client.responses.create(
                    model=self._model_name,
                    input=query,
                    tools=[{"type": "web_search_preview"}],
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_text
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")

    @with_async_usage_check
    async def web_search_async(self, query: str) -> str:
        span = get_current_span()
        match self._provider:
            case "openai":
                import openai

                client = openai.AsyncOpenAI(api_key=self._api_key)
                response = await client.responses.create(
                    model=self._model_name,
                    input=query,
                    tools=[{"type": "web_search_preview"}],
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_text
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")


class VisionService(LLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 1.0,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url)
        self._temperature = temperature

    def _format_image_content(self, image_content_list: list[bytes]) -> list[dict[str, str]]:
        match self._provider:
            case "openai" | "google":
                import base64

                return [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64.b64encode(image_content).decode('utf-8')}"
                        },
                    }
                    for image_content in image_content_list
                ]
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")

    @with_usage_check
    def get_image_description(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel] = None,
    ) -> str | BaseModel:
        client = None
        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai" | "google":
                import openai

                client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        content = [{"type": "text", "text": text_prompt}]
        content.extend(self._format_image_content(image_content_list))
        messages = [
            {
                "role": "user",
                "content": content,
            }
        ]
        if response_format is not None:

            chat_response = client.beta.chat.completions.parse(
                messages=messages,
                model=self._model_name,
                temperature=self._temperature,
                response_format=response_format,
            )
            span.set_attributes(
                {
                    SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: chat_response.usage.completion_tokens,
                    SpanAttributes.LLM_TOKEN_COUNT_PROMPT: chat_response.usage.prompt_tokens,
                    SpanAttributes.LLM_TOKEN_COUNT_TOTAL: chat_response.usage.total_tokens,
                }
            )
            return chat_response.choices[0].message.parsed
        else:
            chat_response = client.chat.completions.create(
                messages=messages,
                model=self._model_name,
                temperature=self._temperature,
            )
            span.set_attributes(
                {
                    SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: chat_response.usage.completion_tokens,
                    SpanAttributes.LLM_TOKEN_COUNT_PROMPT: chat_response.usage.prompt_tokens,
                    SpanAttributes.LLM_TOKEN_COUNT_TOTAL: chat_response.usage.total_tokens,
                }
            )
            return chat_response.choices[0].message.content

    @with_async_usage_check
    async def get_image_description_async(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel] = None,
    ) -> str | BaseModel:
        client = None
        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai" | "google":
                import openai

                client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        content = [{"type": "text", "text": text_prompt}]
        content.extend(self._format_image_content(image_content_list))
        messages = [
            {
                "role": "user",
                "content": content,
            }
        ]
        if response_format is not None:

            chat_response = await client.beta.chat.completions.parse(
                messages=messages,
                model=self._model_name,
                temperature=self._temperature,
                response_format=response_format,
            )
            span.set_attributes(
                {
                    SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: chat_response.usage.completion_tokens,
                    SpanAttributes.LLM_TOKEN_COUNT_PROMPT: chat_response.usage.prompt_tokens,
                    SpanAttributes.LLM_TOKEN_COUNT_TOTAL: chat_response.usage.total_tokens,
                }
            )
            return chat_response.choices[0].message.parsed
        else:
            chat_response = await client.chat.completions.create(
                messages=messages,
                model=self._model_name,
                temperature=self._temperature,
            )
            span.set_attributes(
                {
                    SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: chat_response.usage.completion_tokens,
                    SpanAttributes.LLM_TOKEN_COUNT_PROMPT: chat_response.usage.prompt_tokens,
                    SpanAttributes.LLM_TOKEN_COUNT_TOTAL: chat_response.usage.total_tokens,
                }
            )
            return chat_response.choices[0].message.content


class OCRService(LLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "mistral",
        model_name: str = "mistral-ocr-latest",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url)

    def get_ocr_text(self, messages: list[dict]) -> str:

        match self._provider:
            case "mistral":
                import mistralai

                client = mistralai.Mistral(api_key=self._api_key)
                mistral_compatible_messages = make_mistral_ocr_compatible(messages)
                if mistral_compatible_messages is None:
                    raise ValueError("No OCR compatible messages found")
                ocr_response = client.ocr.process(
                    model="mistral-ocr-latest",
                    document=mistral_compatible_messages,
                    include_image_base64=True,
                )
                # TODO: have a better way to show the response
                return ocr_response.model_dump_json()

            case _:
                raise ValueError(f"Invalid provider for OCR: {self._provider}")

    async def get_ocr_text_async(self, messages: list[dict]) -> str:

        match self._provider:
            case "mistral":
                import mistralai

                client = mistralai.Mistral(api_key=self._api_key)
                mistral_compatible_messages = make_mistral_ocr_compatible(messages)
                if mistral_compatible_messages is None:
                    raise ValueError("No OCR compatible messages found")
                ocr_response = client.ocr.process(
                    model="mistral-ocr-latest",
                    document=mistral_compatible_messages,
                    include_image_base64=True,
                )
                # TODO: have a better way to show the response
                return ocr_response.model_dump_json()
            case _:
                raise ValueError(f"Invalid provider for OCR: {self._provider}")
