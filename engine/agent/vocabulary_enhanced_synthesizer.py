from pydantic import BaseModel

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.synthesizer import Synthesizer, SynthesizerResponse
from engine.agent.build_context import build_context_from_source_chunks
from engine.agent.agent import SourceChunk, SourcedResponse, TermDefinition
from engine.agent.synthesizer_prompts import get_vocabulary_synthesizer_prompt_template
from engine.llm_services.llm_service import LLMService
from engine.trace.trace_manager import TraceManager
from engine.agent.build_context import build_context_from_vocabulary_chunks


class VocabularyEnhancedSynthesizer(Synthesizer):
    def __init__(
        self,
        llm_service: LLMService,
        trace_manager: TraceManager,
        prompt_template: str = get_vocabulary_synthesizer_prompt_template(),
        response_format: BaseModel = SynthesizerResponse,
    ) -> None:
        super().__init__(
            llm_service=llm_service,
            trace_manager=trace_manager,
            prompt_template=prompt_template,
            response_format=response_format,
        )

    def get_response(
        self,
        vocabulary_chunks: list[TermDefinition],
        chunks: list[SourceChunk],
        query_str: str,
    ) -> SourcedResponse:

        context_str = build_context_from_source_chunks(
            sources=chunks,
            llm_metadata_keys=chunks[0].metadata.keys() if chunks else [],
        )
        vocabulary_context = build_context_from_vocabulary_chunks(vocabulary_chunks=vocabulary_chunks)
        with self.trace_manager.start_span(self.__class__.__name__) as span:
            input_str = self._prompt_template.format(
                vocabulary_context_str=vocabulary_context,
                context_str=context_str,
                query_str=query_str,
            )
            response = self._llm_service.constrained_complete(
                messages=[
                    {
                        "role": "system",
                        "content": input_str,
                    },
                ],
                response_format=self.response_format,
            )
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                    SpanAttributes.INPUT_VALUE: input_str,
                    SpanAttributes.OUTPUT_VALUE: response.response,
                }
            )
            span.set_status(trace_api.StatusCode.OK)
            response = SourcedResponse(
                response=response.response,
                sources=chunks,
                is_successful=response.is_successful,
            )
            return response
