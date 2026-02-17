import json
from abc import ABC, abstractmethod
from typing import Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues, RerankerAttributes, SpanAttributes
from opentelemetry import trace as trace_api

from engine.components.types import ComponentAttributes, SourceChunk
from engine.trace.serializer import serialize_to_json
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
            input_documents = [{"content": chunk.content, "id": chunk.name} for chunk in chunks]
            input_data = {"input_documents": input_documents}

            reranker_chunks = await self._rerank_without_trace(query, chunks)

            span.set_attributes({
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RERANKER.value,
                SpanAttributes.INPUT_VALUE: serialize_to_json(input_data, shorten_string=False),
                RerankerAttributes.RERANKER_QUERY: query,
                RerankerAttributes.RERANKER_MODEL_NAME: self._model,
                "component_instance_id": (
                    str(self.component_attributes.component_instance_id)
                    if self.component_attributes.component_instance_id is not None
                    else None
                ),
            })

            for i, chunk in enumerate(chunks):
                retrieval_rank = chunk.metadata.get("_retrieval_rank")
                input_prefix = f"{RerankerAttributes.RERANKER_INPUT_DOCUMENTS}.{i}.document"
                span.set_attributes({
                    f"{input_prefix}.content": chunk.content,
                    f"{input_prefix}.id": chunk.name,
                    f"{input_prefix}.metadata.retrieval_rank": retrieval_rank,
                })

            for i, reranker_chunk in enumerate(reranker_chunks):
                reranker_chunk.metadata["_reranker_rank"] = i + 1

                metadata_str = json.dumps(reranker_chunk.metadata)
                retrieval_rank = reranker_chunk.metadata.get("_retrieval_rank")
                output_prefix = f"{RerankerAttributes.RERANKER_OUTPUT_DOCUMENTS}.{i}.document"
                span.set_attributes({
                    f"{output_prefix}.content": reranker_chunk.content,
                    f"{output_prefix}.id": reranker_chunk.name,
                    f"{output_prefix}.score": reranker_chunk.metadata["reranked_score"],
                    f"{output_prefix}.metadata": metadata_str,
                    f"{output_prefix}.metadata.retrieval_rank": retrieval_rank,
                    f"{output_prefix}.metadata.reranker_rank": i + 1,
                })
            span.set_status(trace_api.StatusCode.OK)
            return reranker_chunks
