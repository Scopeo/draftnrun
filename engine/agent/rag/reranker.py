from abc import ABC, abstractmethod
import json
from typing import Optional

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes, RerankerAttributes

from engine.agent.agent import ComponentAttributes, SourceChunk
from engine.trace.trace_manager import TraceManager


class Reranker(ABC):
    def __init__(
        self,
        trace_manager: TraceManager,
        model: str,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        self.trace_manager = trace_manager
        self._model = model
        self.component_attributes = component_attributes or ComponentAttributes(
            component_instance_name=self.__class__.__name__,
            component_instance_id=None,
        )

    @abstractmethod
    async def _rerank_without_trace(self, query, chunks: list[SourceChunk]) -> list[SourceChunk]:
        pass

    async def rerank(self, query, chunks: list[SourceChunk]):
        with self.trace_manager.start_span(self.component_attributes.component_instance_name) as span:
            reranker_chunks = await self._rerank_without_trace(query, chunks)
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RERANKER.value,
                    RerankerAttributes.RERANKER_QUERY: query,
                    RerankerAttributes.RERANKER_MODEL_NAME: self._model,
                    "component_instance_id": str(self.component_attributes.component_instance_id),
                }
            )

            for i, chunk in enumerate(chunks):
                span.set_attributes(
                    {
                        f"{RerankerAttributes.RERANKER_INPUT_DOCUMENTS}.{i}.document.content": chunk.content,
                        f"{RerankerAttributes.RERANKER_INPUT_DOCUMENTS}.{i}.document.id": chunk.name,
                    }
                )

            for i, reranker_chunk in enumerate(reranker_chunks):
                metadata_str = json.dumps(reranker_chunk.metadata)
                span.set_attributes(
                    {
                        f"{RerankerAttributes.RERANKER_OUTPUT_DOCUMENTS}.{i}.document.content": reranker_chunk.content,
                        f"{RerankerAttributes.RERANKER_OUTPUT_DOCUMENTS}.{i}.document.id": reranker_chunk.name,
                        f"{RerankerAttributes.RERANKER_OUTPUT_DOCUMENTS}.{i}.document.score": reranker_chunk.metadata[
                            "reranked_score"
                        ],
                        f"{RerankerAttributes.RERANKER_OUTPUT_DOCUMENTS}.{i}.document.metadata": metadata_str,
                    }
                )
            span.set_status(trace_api.StatusCode.OK)
            return reranker_chunks
