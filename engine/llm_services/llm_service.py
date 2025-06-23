import os
from typing import Optional
from abc import ABC
from pydantic import BaseModel

from engine.trace.trace_manager import TraceManager
from engine.agent.agent import ToolDescription
from engine.agent.utils import load_str_to_json
from engine.llm_services.constrained_output_models import OutputFormatModel
from settings import settings


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
        temperature: float = 0.5,
        stream: bool = False,
    ) -> str:
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.responses.create(
                    model=self._model_name,
                    input=messages,
                    temperature=temperature,
                    stream=stream,
                )
                return response.output_text
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")

    def constrained_complete(
        self,
        messages: list[dict] | str,
        response_format: BaseModel | str,
        temperature: float = 0.5,
        stream: bool = False,
        tools: list[ToolDescription] = None,
        tool_choice: str = "auto",
    ) -> BaseModel:
        kwargs = {
            "input": messages,
            "model": self._model_name,
            "temperature": temperature,
            "stream": stream,
        }
        if isinstance(response_format, str):
            response_format = load_str_to_json(response_format)
            # validate with the basemodel OutputFormatModel
            response_format["strict"] = True
            response_format["type"] = "json_schema"
            response_format = OutputFormatModel(**response_format).model_dump(exclude_none=True, exclude_unset=True)
            kwargs["text"] = {"format": response_format}
        elif issubclass(response_format, BaseModel):
            kwargs["text_format"] = response_format
        else:
            raise ValueError("response_format must be a string or a BaseModel subclass.")

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
        temperature: float = 0.5,
        stream: bool = False,
        tools: list[ToolDescription] = None,
        tool_choice: str = "auto",
    ) -> str:
        if tools is None:
            tools = []
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.responses.create(
                    model=self._model_name,
                    input=messages,
                    tools=tools,
                    temperature=temperature,
                    stream=stream,
                    tool_choice=tool_choice,
                )
                return response.output_text
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")

    def web_search(self, query: str) -> str:
        match self._provider:
            case "openai":
                import openai

                client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                response = client.responses.create(
                    model=self._model_name,
                    input=query,
                    tools=[{"type": "web_search_preview"}],
                )
                return response.output_text
            case _:
                raise ValueError(f"Invalid provider: {self._provider}")
