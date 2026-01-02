from typing import Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api
from pydantic import BaseModel

from engine.agent.build_context import build_context_from_source_chunks
from engine.agent.synthesizer_prompts import get_base_synthetizer_prompt_template
from engine.agent.types import ComponentAttributes, SourceChunk, SourcedResponse
from engine.agent.utils_prompt import fill_prompt_template
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_manager import TraceManager


class SynthesizerResponse(BaseModel):
    response: str
    is_successful: bool


class Synthesizer:
    def __init__(
        self,
        completion_service: CompletionService,
        trace_manager: TraceManager,
        prompt_template: str = get_base_synthetizer_prompt_template(),
        response_format: BaseModel = SynthesizerResponse,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        self._prompt_template = prompt_template
        self._completion_service = completion_service
        self.response_format = response_format
        self.trace_manager = trace_manager
        self.component_attributes = component_attributes or ComponentAttributes(
            component_instance_name=self.__class__.__name__,
        )

    async def get_response(
        self, chunks: list[SourceChunk], query_str: str, optional_contexts: Optional[dict]
    ) -> SourcedResponse:
        context_str = build_context_from_source_chunks(
            sources=chunks,
            llm_metadata_keys=chunks[0].metadata.keys() if chunks else [],
        )

        with self.trace_manager.start_span(self.component_attributes.component_instance_name) as span:
            input_dict = {"context_str": context_str, "query_str": query_str, **optional_contexts}
            input_str = fill_prompt_template(
                prompt_template=self._prompt_template,
                component_name=self.component_attributes.component_instance_name,
                variables=input_dict,
            )
            span.set_attributes({
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                SpanAttributes.INPUT_VALUE: input_str,
                SpanAttributes.LLM_MODEL_NAME: self._completion_service._model_name,
                "component_instance_id": (
                    str(self.component_attributes.component_instance_id)
                    if self.component_attributes.component_instance_id is not None
                    else None
                ),
                "model_id": (
                    str(self._completion_service._model_id) if self._completion_service._model_id is not None else None
                ),
            })
            response = await self._completion_service.constrained_complete_with_pydantic_async(
                messages=input_str,
                response_format=self.response_format,
            )
            span.set_attributes({
                SpanAttributes.OUTPUT_VALUE: response.response,
            })
            span.set_status(trace_api.StatusCode.OK)
            response = SourcedResponse(
                response=response.response,
                sources=chunks,
                is_successful=response.is_successful,
            )
            return response
