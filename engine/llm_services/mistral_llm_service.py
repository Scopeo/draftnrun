import base64
import json
from typing import Optional
from pydantic import BaseModel

from openai.types.chat import ChatCompletion
from openai.types import Embedding
from mistralai import Mistral
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import ToolDescription
from engine.llm_services.llm_service import LLMService
from engine.trace.trace_manager import TraceManager
from settings import settings


class MistralLLMService(LLMService):
    def __init__(
        self,
        trace_manager: TraceManager,
        model_name: str = "pixtral-12b-2409",
        embedding_model: str = "mistral-embed",
        default_temperature: float = 0.7,
        api_key: Optional[str] = None,
    ):
        super().__init__(trace_manager)
        if api_key is None:
            api_key = settings.MISTRAL_API_KEY
        self._completion_model: str = model_name
        self._embedding_model: str = embedding_model
        self._default_temperature: float = default_temperature
        self._client = Mistral(api_key=api_key)
        self._async_client = None

    # Mimicking the aysnc logic for Mistral with the context manager
    async def __aenter__(self):
        self._async_client = await Mistral(api_key=settings.MISTRAL_API_KEY).__aenter__()
        return self

    async def __aexit__(self, *args):
        await self._async_client.__aexit__(*args)

    def embed(
        self,
        input_text: str | list[str],
    ) -> list[Embedding]:
        return self._client.embeddings.create(
            model=self._embedding_model,
            inputs=input_text,
        ).data

    def complete(
        self,
        messages: list[dict],
        temperature: float = None,
    ) -> ChatCompletion:
        temperature = temperature or self._default_temperature
        with self.trace_manager.start_span("mistral_llm_service.complete") as span:
            span.set_attributes({
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                SpanAttributes.LLM_MODEL_NAME: self._completion_model,
                SpanAttributes.INPUT_VALUE: str(messages),
            })
            for i, msg in enumerate(messages):
                span.set_attributes({f"llm.input_messages.{i}.message.role": msg["role"]})
                if isinstance(msg["content"], list):
                    for j, content in enumerate(msg["content"]):
                        content_type = content["type"]
                        if content_type == "image_url":
                            span.set_attributes({
                                f"llm.input_messages.{i}.message.contents.{j}.message_content.type": "image",
                                f"llm.input_messages.{i}.message.contents.{j}.message_content.image.image.url": content[content_type],
                            })
                        else:
                            span.set_attributes({
                                f"llm.input_messages.{i}.message.contents.{j}.message_content.type": content_type,
                                f"llm.input_messages.{i}.message.contents.{j}.message_content.{content_type}": content[content_type],
                            })
                else:
                    span.set_attributes({
                        f"llm.input_messages.{i}.message.content": msg["content"],
                    })

            response = self._client.chat.complete(
                model=self._completion_model,
                messages=messages,
                temperature=temperature,
            )

            span.set_attributes({
                "llm.output_messages.0.message.content": response.choices[0].message.content,
                "llm.output_messages.0.message.role": response.choices[0].message.role,
                "llm.token_count.total": response.usage.total_tokens,
                SpanAttributes.OUTPUT_VALUE: str(response),
            })

        return response

    def _function_call_without_trace(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        raise NotImplementedError

    def constrained_complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = None,
        response_format: BaseModel = None,
    ) -> BaseModel:
        temperature = temperature or self._default_temperature
        response = self._client.chat.complete(
            model=self._completion_model,
            messages=messages,
            temperature=temperature,
            response_format={
                "type": "json_object",
                "json_schema": {
                    "strict": True,
                    "name": response_format.__name__,
                    "schema": response_format.model_json_schema(),
                },
            },
        )
        processed_data = json.loads(response.choices[0].message.content)
        structured_output = response_format(**processed_data)
        return structured_output

    def generate_transcript(self, audio_path: str, language: str) -> str:
        raise NotImplementedError

    def generate_speech_from_text(self, transcription: str, speech_audio_path: str) -> str:
        raise NotImplementedError

    def _format_image_content(self, image_content_list: list[bytes]) -> list[dict[str, str]]:
        return [
            {
                "type": "image_url",
                "image_url": f"data:image/jpeg;base64,{base64.b64encode(image_content).decode('utf-8')}",
            }
            for image_content in image_content_list
        ]

    # ========== ASYNC METHODS ==========

    async def async_embed(self, input_text: str | list[str]) -> list[Embedding]:
        response = await self._async_client.embeddings.create(
            model=self._embedding_model,
            inputs=input_text,
        )
        return response.data

    async def async_complete(self, messages: list[dict], temperature: float = None) -> str:
        temperature = temperature or self._default_temperature
        response = await self._async_client.chat.complete_async(
            model=self._completion_model,
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content

    async def async_constrained_complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = None,
        response_format: BaseModel = None,
    ) -> BaseModel:
        temperature = temperature or self._default_temperature
        response = await self._async_client.chat.complete_async(
            model=self._completion_model,
            messages=messages,
            temperature=temperature,
            response_format={
                "type": "json_object",
                "json_schema": {
                    "strict": True,
                    "name": response_format.__name__,
                    "schema": response_format.model_json_schema(),
                },
            },
        )
        processed_data = json.loads(response.choices[0].message.content)
        return response_format(**processed_data)

    async def async_function_call_without_trace(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        tools: Optional[list[ToolDescription]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletion:
        raise NotImplementedError

    async def async_generate_transcript(self, audio_path: str, language: str) -> str:
        raise NotImplementedError

    async def async_generate_speech_from_text(self, transcription: str, speech_audio_path: str) -> str:
        raise NotImplementedError

    async def async_complete_with_files(
        self,
        messages: list[dict],
        files: list[bytes],
        temperature: float = None,
    ) -> str:
        raise NotImplementedError
