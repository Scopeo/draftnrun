from typing import Optional
from abc import ABC
from pydantic import BaseModel

from engine.trace.trace_manager import TraceManager
from engine.agent.agent import ToolDescription
from engine.agent.utils import load_str_to_json
from engine.llm_services.constrained_output_models import OutputFormatModel
from settings import settings
from engine.llm_services.utils import chat_completion_to_response
from openai.types.chat import ChatCompletion


class LLMService(ABC):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str,
        model_name: str,
        api_key: Optional[str] = None,
    ):
        self._trace_manager = trace_manager
        self._provider = provider
        self._model_name = model_name
        self._api_key = api_key


class EmbeddingService(LLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "text-embedding-3-large",
        api_key: Optional[str] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key)

    def embed_text(self, text: str) -> list[float]:
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.embeddings.create(
                    model=self._model_name,
                    input=text,
                )
                return response.data
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")


class CompletionService(LLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        temperature: float = 0.5,
    ):
        super().__init__(trace_manager, provider, model_name, api_key)
        self._temperature = temperature

    def complete(
        self,
        messages: list[dict] | str,
        stream: bool = False,
    ) -> str:
        match self._provider:
            case "openai":
                import openai

                messages = chat_completion_to_response(messages)
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.responses.create(
                    model=self._model_name,
                    input=messages,
                    temperature=self._temperature,
                    stream=stream,
                )
                return response.output_text
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")

    def constrained_complete_with_pydantic(
        self,
        messages: list[dict] | str,
        response_format: BaseModel,
        stream: bool = False,
        tools: list[ToolDescription] = None,
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

        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.responses.parse(**kwargs)
                return response.output_parsed
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")

    def constrained_complete_with_json_schema(
        self,
        messages: list[dict] | str,
        response_format: str,
        stream: bool = False,
        tools: list[ToolDescription] = None,
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

        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.responses.parse(**kwargs)
                return response.output_text
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")

    def function_call(
        self,
        messages: list[dict] | str,
        stream: bool = False,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        if tools is None:
            tools = []
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                openai_tools = [tool.openai_format for tool in tools]
                response = client.chat.completions.create(
                    model=self._model_name,
                    messages=messages,
                    tools=openai_tools,
                    temperature=self._temperature,
                    stream=stream,
                    tool_choice=tool_choice,
                )
                return response
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")


class WebSearchService(LLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        provider: str = "openai",
        model_name: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
    ):
        super().__init__(trace_manager, provider, model_name, api_key)

    def web_search(self, query: str) -> str:
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.responses.create(
                    model=self._model_name,
                    input=query,
                    tools=[{"type": "web_search_preview"}],
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
        temperature: float = 1.0,
    ):
        super().__init__(trace_manager, provider, model_name, api_key)
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

    def get_image_description(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: Optional[BaseModel] = None,
    ) -> str | BaseModel:
        client = None
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            case "google":
                import openai

                client = openai.OpenAI(api_key=settings.GOOGLE_API_KEY, base_url=settings.GOOGLE_API_KEY)
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
            return chat_response.choices[0].message.parsed
        else:
            chat_response = client.chat.completions.create(
                messages=messages,
                model=self._model_name,
                temperature=self._temperature,
            )
            return chat_response.choices[0].message.content
