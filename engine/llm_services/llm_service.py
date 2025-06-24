import abc
import json
from typing import Optional

from pydantic import BaseModel
from openai.types.chat import ChatCompletion
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.trace.trace_manager import TraceManager
from engine.agent.agent import ToolDescription


class LLMService(abc.ABC):
    def __init__(self, trace_manager: TraceManager):
        self.trace_manager = trace_manager
        self._completion_model: str = None
        self._embedding_model: str = None
        self._default_temperature: float = None

    @abc.abstractmethod
    def embed(self, input_text: str | list[str]) -> str:
        pass

    @abc.abstractmethod
    def complete(self, messages: list[dict], temperature: float = None) -> str:
        pass

    @abc.abstractmethod
    def complete_with_files(self, messages: list[dict], files: list[bytes], temperature: float = None) -> str:
        pass

    @abc.abstractmethod
    def _function_call_without_trace(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        pass

    def function_call(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        if tools is None:
            tools = []
        temperature = temperature or self._default_temperature
        span_name = "FunctionCall"
        with self.trace_manager.start_span(span_name) as span:
            response = self._function_call_without_trace(
                messages=messages,
                temperature=temperature,
                tools=tools,
                tool_choice=tool_choice,
            )

            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                }
            )
            for i, msg in enumerate(messages):
                if "content" in msg:
                    span.set_attributes(
                        {
                            f"llm.input_messages.{i}.message.content": msg["content"],
                        }
                    )
                if "role" in msg:
                    span.set_attributes(
                        {
                            f"llm.input_messages.{i}.message.role": msg["role"],
                        }
                    )

            # TODO: Find more elegant presentation on observability
            input_tools = {
                "available_tools": [tool.openai_format for tool in tools],
            }
            tool_calls = response.choices[0].message.tool_calls or []
            output_tools = {
                "output_tools": {
                    f"{tool_call.function.name}": {
                        "tool_call_id": tool_call.id,
                        "tool_call_arguments_json": tool_call.function.arguments,
                    }
                    for tool_call in tool_calls
                },
            }

            span.set_attributes(
                {
                    SpanAttributes.INPUT_VALUE: json.dumps(input_tools, indent=2),
                    SpanAttributes.OUTPUT_VALUE: json.dumps(output_tools, indent=2),
                }
            )

        return response

    @abc.abstractmethod
    def constrained_complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = None,
        response_format: BaseModel = None,
    ) -> BaseModel:
        pass

    @abc.abstractmethod
    def generate_transcript(self, audio_path: str, language: str) -> str:
        pass

    @abc.abstractmethod
    def generate_speech_from_text(self, transcription: str, speech_audio_path: str) -> str:
        pass

    @abc.abstractmethod
    def _format_image_content(self, image_content_list: list[bytes]) -> list[dict[str, str]]:
        pass

    def get_image_description(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: BaseModel = None,
    ) -> str | BaseModel:
        content = [{"type": "text", "text": text_prompt}]
        content.extend(self._format_image_content(image_content_list))
        messages = [
            {
                "role": "user",
                "content": content,
            }
        ]
        if response_format is not None:
            chat_response = self.constrained_complete(
                messages=messages,
                response_format=response_format,
            )

        else:
            chat_response = self.complete(
                messages=messages,
            )

        return chat_response

    @abc.abstractmethod
    def get_token_size(self, content: str) -> int:
        pass

    @abc.abstractmethod
    async def aembed(self, input_text: str | list[str]) -> list[str]:
        pass

    @abc.abstractmethod
    async def acomplete(self, messages: list[dict], temperature: float = None) -> str:
        pass

    @abc.abstractmethod
    async def aconstrained_complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = None,
        response_format: BaseModel = None,
    ) -> BaseModel:
        pass

    @abc.abstractmethod
    async def agenerate_transcript(self, audio_path: str, language: str) -> str:
        pass

    @abc.abstractmethod
    async def agenerate_speech_from_text(self, transcription: str, speech_audio_path: str) -> str:
        pass

    @abc.abstractmethod
    async def acomplete_with_files(
        self,
        messages: list[dict],
        files: list[bytes],
        temperature: float = None,
    ) -> str:
        pass

    @abc.abstractmethod
    async def afunction_call_without_trace(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        pass

    async def afunction_call(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        if tools is None:
            tools = []
        temperature = temperature or self._default_temperature
        span_name = "FunctionCall"
        with self.trace_manager.start_span(span_name) as span:
            response = await self.afunction_call_without_trace(
                messages=messages,
                temperature=temperature,
                tools=tools,
                tool_choice=tool_choice,
            )

            span.set_attributes({SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value})
            for i, msg in enumerate(messages):
                if "content" in msg:
                    span.set_attributes({f"llm.input_messages.{i}.message.content": msg["content"]})
                if "role" in msg:
                    span.set_attributes({f"llm.input_messages.{i}.message.role": msg["role"]})

            input_tools = {"available_tools": [tool.openai_format for tool in tools]}
            tool_calls = response.choices[0].message.tool_calls or []
            output_tools = {
                "output_tools": {
                    f"{tool_call.function.name}": {
                        "tool_call_id": tool_call.id,
                        "tool_call_arguments_json": tool_call.function.arguments,
                    }
                    for tool_call in tool_calls
                }
            }

            span.set_attributes({
                SpanAttributes.INPUT_VALUE: json.dumps(input_tools, indent=2),
                SpanAttributes.OUTPUT_VALUE: json.dumps(output_tools, indent=2),
            })

        return response

    async def aget_image_description(
        self,
        image_content_list: list[bytes],
        text_prompt: str,
        response_format: BaseModel = None,
    ) -> str | BaseModel:
        content = [{"type": "text", "text": text_prompt}]
        content.extend(self._format_image_content(image_content_list))
        messages = [{"role": "user", "content": content}]
        if response_format is not None:
            return await self.aconstrained_complete(messages=messages, response_format=response_format)
        return await self.acomplete(messages=messages)
