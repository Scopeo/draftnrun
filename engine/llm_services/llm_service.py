import json
import logging
import asyncio
from functools import wraps
from typing import Optional
from abc import ABC
from pydantic import BaseModel
import base64

from opentelemetry.trace import get_current_span
from openinference.semconv.trace import SpanAttributes

from engine.llm_services.utils import (
    check_usage,
    validate_and_extract_json_response,
    make_messages_compatible_for_mistral,
    make_mistral_ocr_compatible,
    convert_tool_description_to_output_format,
    wrap_str_content_into_chat_completion_message,
)
from engine.trace.trace_manager import TraceManager
from engine.agent.types import ToolDescription
from engine.agent.utils import load_str_to_json
from engine.llm_services.constrained_output_models import (
    OutputFormatModel,
    format_prompt_with_pydantic_output,
    convert_json_str_to_pydantic,
)
from settings import settings
from engine.llm_services.utils import chat_completion_to_response, build_openai_responses_kwargs
from openai.types.chat import ChatCompletion

LOGGER = logging.getLogger(__name__)

DEFAULT_TEMPERATURE = 1


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
        if self._api_key is None:
            match self._provider:
                case "openai":
                    self._api_key = settings.OPENAI_API_KEY
                case "cerebras":
                    self._api_key = settings.CEREBRAS_API_KEY
                case "google":
                    self._api_key = settings.GOOGLE_API_KEY
                case "mistral":
                    self._api_key = settings.MISTRAL_API_KEY
                case _:
                    custom_models_dict = settings.custom_models.get("custom_models")
                    if custom_models_dict is None:
                        raise ValueError(f"Custom models configuration not found in settings")
                    config_provider = custom_models_dict.get(self._provider)
                    if config_provider is None:
                        raise ValueError(f"Provider {self._provider} not found in settings")
                    model_config = next(
                        (model for model in config_provider if model.get("model_name") == self._model_name), None
                    )
                    if model_config is None:
                        raise ValueError(f"Model {self._model_name} not found for provider {self._provider}")
                    self._api_key = model_config.get("api_key")
                    LOGGER.debug(f"Using custom api key for provider: {self._provider}")
                    if self._api_key is None:
                        raise ValueError(f"API key must be provided for custom provider: {self._provider}")

        if self._base_url is None:
            match self._provider:
                case "openai":
                    self._base_url = None
                case "cerebras":
                    self._base_url = settings.CEREBRAS_BASE_URL
                case "google":
                    self._base_url = settings.GOOGLE_BASE_URL
                case "mistral":
                    self._base_url = settings.MISTRAL_BASE_URL
                case _:
                    custom_models_dict = settings.custom_models.get("custom_models")
                    if custom_models_dict is None:
                        raise ValueError(f"Custom models configuration not found in settings")
                    config_provider = custom_models_dict.get(self._provider)
                    if config_provider is None:
                        raise ValueError(f"Provider {self._provider} not found in settings")
                    model_config = next(
                        (model for model in config_provider if model.get("model_name") == self._model_name), None
                    )
                    if model_config is None:
                        raise ValueError(f"Model {self._model_name} not found for provider {self._provider}")
                    self._base_url = model_config.get("base_url")
                    LOGGER.debug(f"Using custom base url for provider: {self._provider}")
                    if self._base_url is None:
                        raise ValueError(f"Base URL must be provided for custom provider: {self._provider}")


class EmbeddingService(LLMService):
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

    def embed_text(self, text: str) -> list[float]:
        return asyncio.run(self.embed_text_async(text))

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
        temperature: float = DEFAULT_TEMPERATURE,
        verbosity: Optional[str] = None,
        reasoning: Optional[str] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url)
        self._invocation_parameters = {"temperature": temperature}
        if verbosity is not None:
            self._invocation_parameters["verbosity"] = verbosity
        if reasoning is not None:
            self._invocation_parameters["reasoning"] = reasoning

    @with_usage_check
    def complete(
        self,
        messages: list[dict] | str,
        stream: bool = False,
    ) -> str:
        return asyncio.run(self.complete_async(messages, stream))

    @with_async_usage_check
    async def complete_async(
        self,
        messages: list[dict] | str,
        stream: bool = False,
    ) -> str:
        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps(self._invocation_parameters)})
        match self._provider:
            case "openai":
                import openai

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY
                messages = chat_completion_to_response(messages)
                client = openai.AsyncOpenAI(api_key=self._api_key)
                kwargs_create = build_openai_responses_kwargs(
                    self._model_name,
                    self._invocation_parameters.get("verbosity"),
                    self._invocation_parameters.get("reasoning"),
                    self._invocation_parameters.get("temperature"),
                    {"model": self._model_name, "input": messages, "stream": stream},
                )
                response = await client.responses.create(**kwargs_create)
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
                    temperature=self._invocation_parameters.get("temperature"),
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
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> BaseModel:
        return asyncio.run(
            self.constrained_complete_with_pydantic_async(
                messages,
                response_format,
                stream,
                tools=tools,
                tool_choice=tool_choice,
            )
        )

    async def _fallback_constrained_complete_with_json_format(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        stream: bool = False,
    ) -> tuple[BaseModel, int, int, int]:
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
            temperature=self._invocation_parameters.get("temperature"),
            stream=stream,
            response_format=response_format_schema,
        )
        response_dict = json.loads(response.choices[0].message.content)
        return (
            response_format(**response_dict),
            response.usage.completion_tokens,
            response.usage.prompt_tokens,
            response.usage.total_tokens,
        )

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
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps(self._invocation_parameters)})
        match self._provider:
            case "openai":
                import openai

                # Transform messages for OpenAI response API
                messages = chat_completion_to_response(messages)
                kwargs = build_openai_responses_kwargs(
                    self._model_name,
                    self._invocation_parameters.get("verbosity"),
                    self._invocation_parameters.get("reasoning"),
                    self._invocation_parameters.get("temperature"),
                    {"input": messages, "model": self._model_name, "stream": stream, "text_format": response_format},
                )

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

            case "mistral":
                import mistralai

                client = mistralai.Mistral(api_key=self._api_key)
                # Convert messages format if needed
                if isinstance(messages, str):
                    messages = [{"role": "user", "content": messages}]
                response = await client.chat.parse_async(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._invocation_parameters.get("temperature"),
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

            case "cerebras" | "google" | _:
                # TODO: modify to make it work with  models not handling response format
                try:
                    (
                        answer,
                        usage_completion_tokens,
                        usage_prompt_tokens,
                        usage_total_tokens,
                    ) = await self._fallback_constrained_complete_with_json_format(
                        messages=messages,
                        response_format=response_format,
                        stream=stream,
                    )
                except Exception as e:
                    LOGGER.error(f"Error in constrained_complete_with_pydantic_async: {e}")
                    raise ValueError(
                        "Error processing constrained completion"
                        f" with pydantic schema on the model {self._model_name} : {str(e)}"
                    )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: usage_completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: usage_prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: usage_total_tokens,
                    }
                )
                return answer

    async def _default_constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: dict,
        stream: bool = False,
    ) -> tuple[str, int, int, int]:
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
            temperature=self._invocation_parameters.get("temperature"),
            stream=stream,
            response_format=response_format,
        )
        # Post-process response to handle models that return schema instead of data
        raw_content = response.choices[0].message.content
        processed_content = validate_and_extract_json_response(raw_content, schema)
        return (
            processed_content,
            response.usage.completion_tokens,
            response.usage.prompt_tokens,
            response.usage.total_tokens,
        )

    @with_usage_check
    def constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> str:
        return asyncio.run(
            self.constrained_complete_with_json_schema_async(
                messages, response_format, stream, tools=tools, tool_choice=tool_choice
            )
        )

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
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps(self._invocation_parameters)})
        match self._provider:
            case "openai":
                import openai

                # Transform messages for OpenAI response API
                messages = chat_completion_to_response(messages)
                kwargs = build_openai_responses_kwargs(
                    self._model_name,
                    self._invocation_parameters.get("verbosity"),
                    self._invocation_parameters.get("reasoning"),
                    self._invocation_parameters.get("temperature"),
                    {
                        "input": messages,
                        "model": self._model_name,
                        "stream": stream,
                        "text": {"format": response_format},
                    },
                )

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

            case "mistral":
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

                # Make messages compatible for Mistral API
                mistral_compatible_messages = make_messages_compatible_for_mistral(messages)

                client = openai.AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = await client.chat.completions.create(
                    model=self._model_name,
                    messages=mistral_compatible_messages,
                    temperature=self._invocation_parameters.get("temperature"),
                    stream=stream,
                    response_format=response_format,
                )

                # Post-process response to handle models that return schema instead of data
                raw_content = response.choices[0].message.content
                processed_content = validate_and_extract_json_response(raw_content, schema)

                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return processed_content

            case "cerebras" | "google" | _:
                try:
                    (processed_content, usage_completion_tokens, usage_prompt_tokens, usage_total_tokens) = (
                        await self._default_constrained_complete_with_json_schema(
                            messages=messages,
                            response_format=response_format,
                            stream=stream,
                        )
                    )
                except Exception as e:
                    LOGGER.error(f"Error in constrained_complete_with_json_schema_async: {e}")
                    raise ValueError(
                        "Error processing constrained completion"
                        f" with JSON schema on the provider {self._provider}"
                        f" with model {self._model_name} : {str(e)}"
                    )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: usage_completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: usage_prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: usage_total_tokens,
                    }
                )
                return processed_content

    @with_usage_check
    def function_call(
        self,
        messages: list[dict] | str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        return asyncio.run(self.function_call_async(messages, stream, tools, tool_choice))

    @with_async_usage_check
    async def function_call_async(
        self,
        messages: list[dict] | str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
        structured_output_tool: Optional[ToolDescription] = None,
    ) -> ChatCompletion:
        """
        Main function calling dispatcher that routes to appropriate implementation.
        """
        if structured_output_tool is not None:
            return await self.function_call_with_structured_output_async(
                messages=messages,
                stream=stream,
                tools=tools,
                tool_choice=tool_choice,
                structured_output_tool=structured_output_tool,
            )
        else:
            return await self.function_call_without_structured_output_async(
                messages=messages,
                stream=stream,
                tools=tools,
                tool_choice=tool_choice,
            )

    async def _default_function_call_without_structured_output(
        self,
        messages: list[dict] | str,
        stream: bool,
        tools: list[dict],
        tool_choice: str,
    ) -> tuple[ChatCompletion, int, int, int]:
        import openai

        client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        response = await client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            tools=tools,
            temperature=self._invocation_parameters.get("temperature"),
            stream=stream,
            tool_choice=tool_choice,
        )
        return response, response.usage.completion_tokens, response.usage.prompt_tokens, response.usage.total_tokens

    @with_async_usage_check
    async def function_call_without_structured_output_async(
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
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps(self._invocation_parameters)})

        match self._provider:
            case "openai":
                (response, usage_completion_tokens, usage_prompt_tokens, usage_total_tokens) = (
                    await self._default_function_call_without_structured_output(
                        messages=messages,
                        stream=stream,
                        tools=openai_tools,
                        tool_choice=tool_choice,
                    )
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: usage_completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: usage_prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: usage_total_tokens,
                    }
                )
                return response

            case "google":
                if not openai_tools:
                    empty_function_tool = ToolDescription(
                        **{
                            "name": "empty_function_tool",
                            "description": "This tool does nothing and is to never by used/called.",
                            "tool_properties": {},
                            "required_tool_properties": [],
                        }
                    )
                    openai_tools = [empty_function_tool.openai_format]
                    (response, usage_completion_tokens, usage_prompt_tokens, usage_total_tokens) = (
                        await self._default_function_call_without_structured_output(
                            messages=messages,
                            stream=stream,
                            tools=openai_tools,
                            tool_choice=tool_choice,
                        )
                    )
                    span.set_attributes(
                        {
                            SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: usage_completion_tokens,
                            SpanAttributes.LLM_TOKEN_COUNT_PROMPT: usage_prompt_tokens,
                            SpanAttributes.LLM_TOKEN_COUNT_TOTAL: usage_total_tokens,
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
                    temperature=self._invocation_parameters.get("temperature"),
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
                    temperature=self._invocation_parameters.get("temperature"),
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
    async def function_call_with_structured_output_async(
        self,
        messages: list[dict] | str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
        structured_output_tool: Optional[ToolDescription] = None,
    ) -> ChatCompletion:
        if tools is None:
            tools = []

        openai_tools = [tool.openai_format for tool in tools]

        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps(self._invocation_parameters)})

        # Check for structured output tool early return
        if tool_choice == "none":
            response = await self._constrained_complete_structured_response_without_tools(
                structured_output_tool=structured_output_tool,
                messages=messages,
                stream=stream,
            )
            # Return immediately to avoid duplicated spans in the trace (done in the constrained function)
            return response

        match self._provider:
            case "openai" | "google":
                import openai

                client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

            case "mistral":
                import openai

                mistral_compatible_messages = make_messages_compatible_for_mistral(messages)
                client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
                messages = mistral_compatible_messages  # Use formatted messages

            case _:
                import openai

                client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

        tool_choice = "required"
        openai_tools.append(structured_output_tool.openai_format)

        response = await client.chat.completions.create(
            model=self._model_name,
            messages=messages,
            tools=openai_tools,
            temperature=self._invocation_parameters.get("temperature"),
            stream=stream,
            tool_choice=tool_choice,
        )

        # Ensure that the answer we provide is either:
        # - called tools if no structured output tool was called
        # - structured output if the structured output tool was called in the tools
        # - enforce a structured output if no tools were called (should not happen unless LLM error)
        response = await self.ensure_tools_or_structured_output_response(
            response=response,
            original_messages=messages,
            structured_output_tool=structured_output_tool,
            stream=stream,
        )
        span.set_attributes(
            {
                SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
            }
        )
        return response

    async def _constrained_complete_structured_response_without_tools(
        self,
        structured_output_tool: ToolDescription,
        messages: list[dict] | str,
        stream: bool = False,
    ) -> ChatCompletion:
        """
        Get a structured response when explicitly choosing to answer without tools (tool_choice="none").
        This method calls the regular function calling and then processes the result.
        """
        LOGGER.info("Getting structured response without tools using LLM constrained method")
        structured_json_output = convert_tool_description_to_output_format(structured_output_tool)
        structured_content = await self.constrained_complete_with_json_schema_async(
            messages=messages,
            stream=stream,
            response_format=structured_json_output,
        )
        response = wrap_str_content_into_chat_completion_message(structured_content, self._model_name)
        return response

    async def ensure_tools_or_structured_output_response(
        self,
        response: ChatCompletion,
        original_messages: list[dict],
        structured_output_tool: ToolDescription,
        stream: bool = False,
    ) -> ChatCompletion:
        """
        Ensure the response is formatted as structured output.

        If the structured output tool was called, extract its result.
        If no tools were called, use backup LLM method to force structured formatting.

        Args:
            response: The ChatCompletion response object to modify
            original_messages: The original messages sent to the LLM
            structured_output_tool: The structured output tool description
            stream: Whether to stream the response

        Returns:
            A ChatCompletion object with structured content
        """
        tools_called = response.choices[0].message.tool_calls
        # If no tools were called, use backup method to force structured formatting from the response message
        if not tools_called:
            LOGGER.info(
                "No tools were called, using backup LLM method to format structured output on the whole conversation"
            )
            assistant_message = {
                "role": response.choices[0].message.role,
                "content": response.choices[0].message.content,
            }
            messages = original_messages + [assistant_message]
            return await self._constrained_complete_structured_response_without_tools(
                structured_output_tool=structured_output_tool,
                messages=messages,
                stream=stream,
            )

        if len(tools_called) > 1:
            tools_called_without_structured_output = []
            for call in tools_called:
                if call.function.name == structured_output_tool.name:
                    continue
                tools_called_without_structured_output.append(call)
            response.choices[0].message.tool_calls = tools_called_without_structured_output
        else:
            if tools_called[0].function.name == structured_output_tool.name:
                try:
                    # Return the arguments of the structured output tool as the final response
                    response.choices[0].message.content = json.dumps(
                        tools_called[0].function.arguments, ensure_ascii=False
                    )
                    response.choices[0].message.tool_calls = None
                    return response
                except Exception as e:
                    raise ValueError(f"Error parsing structured output tool response: {e}") from e
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
    def web_search(self, query: str, allowed_domains: Optional[list[str]] = None) -> str:
        return asyncio.run(self.web_search_async(query, allowed_domains))

    @with_async_usage_check
    async def web_search_async(self, query: str, allowed_domains: Optional[list[str]] = None) -> str:
        span = get_current_span()
        match self._provider:
            case "openai":
                import openai

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
        temperature: float = DEFAULT_TEMPERATURE,
    ):
        super().__init__(trace_manager, provider, model_name, api_key, base_url)
        self._temperature = temperature
        self._image_format = None
        match self._provider:
            case "openai" | "google":
                self._image_format = "jpeg"
            case "cerebras":
                raise ValueError("Our implentation of Cerebras does not support vision models.")
            case _:
                custom_models = settings.custom_models["custom_models"][self._provider]
                for model in custom_models:
                    if model.get("name") == self._model_name:
                        self._image_format = model.get("image_format", None)
                        break

                LOGGER.debug(f"Using image format for custom model {self._model_name}: {self._image_format}")
                if self._image_format is None:
                    raise ValueError(
                        f"image format not provided for custom model {self._model_name} "
                        f"for provider {self._provider}"
                    )

    def _format_image_content(self, image_content_list: list[bytes]) -> list[dict[str, str]]:
        return [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{self._image_format};base64,{base64.b64encode(image_content).decode('utf-8')}"
                },
            }
            for image_content in image_content_list
        ]

    @with_usage_check
    def get_image_description(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel] = None,
    ) -> str | BaseModel:
        return asyncio.run(self.get_image_description_async(image_content_list, text_prompt, response_format))

    @with_async_usage_check
    async def get_image_description_async(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel] = None,
    ) -> str | BaseModel:
        span = get_current_span()
        span.set_attributes({SpanAttributes.LLM_INVOCATION_PARAMETERS: json.dumps({"temperature": self._temperature})})
        match self._provider:
            case "openai" | "google":
                import openai

                client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
            case _:
                import openai

                client = openai.AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

                if response_format is not None:
                    text_prompt = format_prompt_with_pydantic_output(text_prompt, response_format)

        content = [{"type": "text", "text": text_prompt}]
        content.extend(self._format_image_content(image_content_list))
        messages = [
            {
                "role": "user",
                "content": content,
            }
        ]
        if response_format is not None:
            match self._provider:
                case "openai" | "google":
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
                case _:
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
                    return convert_json_str_to_pydantic(
                        chat_response.choices[0].message.content,
                        response_format,
                    )
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
        return asyncio.run(self.get_ocr_text_async(messages))

    async def get_ocr_text_async(self, messages: list[dict]) -> str:

        match self._provider:
            case "mistral":
                import mistralai

                client = mistralai.Mistral(api_key=self._api_key)
                mistral_compatible_messages = make_mistral_ocr_compatible(messages)
                if mistral_compatible_messages is None:
                    raise ValueError("No OCR compatible messages found")
                ocr_response = await client.ocr.process_async(
                    model="mistral-ocr-latest",
                    document=mistral_compatible_messages,
                    include_image_base64=True,
                )
                # TODO: have a better way to show the response
                return ocr_response.model_dump_json()
            case _:
                raise ValueError(f"Invalid provider for OCR: {self._provider}")
