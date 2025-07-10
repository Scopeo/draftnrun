import json
from functools import wraps
from typing import Optional
from abc import ABC
from pydantic import BaseModel

from opentelemetry.trace import get_current_span
from openinference.semconv.trace import SpanAttributes

from engine.llm_services.utils import check_usage
from engine.trace.trace_manager import TraceManager
from engine.agent.agent import ToolDescription
from engine.agent.utils import load_str_to_json
from engine.llm_services.constrained_output_models import OutputFormatModel
from settings import settings
from engine.llm_services.utils import chat_completion_to_response
from openai.types.chat import ChatCompletion


def with_usage_check(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        provider = getattr(self, "_provider", None)
        if provider is None:
            raise ValueError("Instance must have a 'provider' attribute to perform usage check.")

        check_usage(provider)
        return func(self, *args, **kwargs)

    return wrapper


def get_api_key_and_base_url(model_name: str) -> tuple[str, str]:
    try:
        for provider, model_info in settings.custom_llm_models.items():
            model_names = model_info.get("model_name")
            if model_name in model_names:
                return model_info.get("api_key"), model_info.get("base_url")
    except Exception as e:
        raise ValueError(f"No api_key and base_url found for model name: {model_name}") from e


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

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY

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

                if self._api_key is None or self._base_url is None:
                    self._api_key, self._base_url = get_api_key_and_base_url(self._model_name)

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

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY
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

            case "cerebras":
                import openai

                if self._api_key is None:
                    self._api_key = settings.CEREBRAS_API_KEY

                client = openai.OpenAI(
                    api_key=self._api_key,
                    base_url="https://api.cerebras.ai/v1",
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

            case _:
                import openai

                if self._api_key is None or self._base_url is None:
                    self._api_key, self._base_url = get_api_key_and_base_url(self._model_name)

                client = openai.OpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                response = client.chat.completions.create(
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
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> BaseModel:
        messages = chat_completion_to_response(messages)
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

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY
                client = openai.OpenAI(api_key=self._api_key)
                response = client.responses.parse(**kwargs)
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_parsed

            case "cerebras":
                import openai

                if self._api_key is None:
                    self._api_key = settings.CEREBRAS_API_KEY

                client = openai.OpenAI(
                    api_key=self._api_key,
                    base_url="https://api.cerebras.ai/v1",
                )
                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                    stream=stream,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": response_format.__name__,
                            "schema": response_format.model_json_schema()
                        }
                    }
                )
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.completion_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.prompt_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response_format.model_validate_json(response.choices[0].message.content)

            case _:
                raise ValueError(f"Invalid provider: {self._provider}")

    @with_usage_check
    def constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> str:
        kwargs = {
            "input": messages,
            "model": self._model_name,
            "temperature": self._temperature,
            "stream": stream,
        }
        messages = chat_completion_to_response(messages)
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

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY
                client = openai.OpenAI(api_key=self._api_key)
                response = client.responses.parse(**kwargs)
                span.set_attributes(
                    {
                        SpanAttributes.LLM_TOKEN_COUNT_COMPLETION: response.usage.output_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_PROMPT: response.usage.input_tokens,
                        SpanAttributes.LLM_TOKEN_COUNT_TOTAL: response.usage.total_tokens,
                    }
                )
                return response.output_text
            case "cerebras":
                import openai

                if self._api_key is None:
                    self._api_key = settings.CEREBRAS_API_KEY

                client = openai.OpenAI(
                    api_key=self._api_key,
                    base_url="https://api.cerebras.ai/v1",
                )
                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    temperature=self._temperature,
                    stream=stream,
                    response_format=response_format
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
                raise ValueError(f"Invalid provider: {self._provider}")

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
            case "openai":
                import openai

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY
                client = openai.OpenAI(api_key=self._api_key)
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
            case "cerebras":
                import openai

                if self._api_key is None:
                    self._api_key = settings.CEREBRAS_API_KEY

                client = openai.OpenAI(
                    api_key=self._api_key,
                    base_url="https://api.cerebras.ai/v1",
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
            case _:
                import openai

                if self._api_key is None or self._base_url is None:
                    self._api_key, self._base_url = get_api_key_and_base_url(self._model_name)

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

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY
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
            case "openai":
                import openai

                if self._api_key is None:
                    self._api_key = settings.OPENAI_API_KEY
                client = openai.OpenAI(api_key=self._api_key)
            case "google":
                import openai

                if self._api_key is None:
                    self._api_key = settings.GOOGLE_API_KEY

                client = openai.OpenAI(api_key=self._api_key, base_url=settings.GOOGLE_BASE_URL)
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
