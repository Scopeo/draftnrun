from typing import Optional
import json

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.types import SourceChunk, ComponentAttributes
from engine.qdrant_service import QdrantService
from engine.trace.trace_manager import TraceManager


def cast_string_to_list(string: Optional[str]) -> list[str]:
    """Cast a comma-separated string into a list of trimmed strings."""
    if not string:
        return []
    return [s.strip() for s in string.split(",") if s.strip()]


class Retriever:
    def __init__(
        self,
        trace_manager: TraceManager,
        qdrant_service: QdrantService,
        collection_name: str,
        max_retrieved_chunks: int,
        enable_date_penalty_for_chunks: bool = False,
        chunk_age_penalty_rate: Optional[float] = None,
        default_penalty_rate: Optional[float] = None,
        metadata_date_key: Optional[str] = None,
        max_retrieved_chunks_after_penalty: Optional[int] = None,
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        self.trace_manager = trace_manager
        self.collection_name = collection_name
        self._max_retrieved_chunks = max_retrieved_chunks
        self._vectorestore_service = qdrant_service
        self.enable_chunk_penalization = enable_date_penalty_for_chunks
        self.chunk_age_penalty_rate = chunk_age_penalty_rate
        self.default_penalty_rate = default_penalty_rate
        self.metadata_date_key = metadata_date_key
        self.max_retrieved_chunks_after_penalty = max_retrieved_chunks_after_penalty
        self.component_attributes = component_attributes or ComponentAttributes(
            component_instance_name=self.__class__.__name__
        )

    async def _get_chunks_without_trace(
        self,
        query_text: str,
        filters: Optional[dict] = None,
    ) -> list[SourceChunk]:
        chunks = await self._vectorestore_service.retrieve_similar_chunks_async(
            query_text=query_text,
            collection_name=self.collection_name,
            limit=self._max_retrieved_chunks,
            filter=filters,
            enable_date_penalty_for_chunks=self.enable_chunk_penalization,
            chunk_age_penalty_rate=self.chunk_age_penalty_rate,
            default_penalty_rate=self.default_penalty_rate,
            metadata_date_key=cast_string_to_list(self.metadata_date_key),
            max_retrieved_chunks_after_penalty=self.max_retrieved_chunks_after_penalty,
        )

        return chunks

    async def get_chunks(
        self,
        query_text: str,
        filters: Optional[dict] = None,
    ) -> list[SourceChunk]:
        with self.trace_manager.start_span(self.component_attributes.component_instance_name) as span:
            chunks = await self._get_chunks_without_trace(
                query_text,
                filters,
            )
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                    SpanAttributes.EMBEDDING_MODEL_NAME: self._vectorestore_service._embedding_service._model_name,
                    SpanAttributes.INPUT_VALUE: query_text,
                    "component_instance_id": str(self.component_attributes.component_instance_id),
                }
            )

            if len(chunks) > 30:
                for i, chunk in enumerate(chunks):
                    metadata_str = json.dumps(chunk.metadata)
                    span.add_event(
                        f"Retrieved Document {i}",
                        {
                            "content": chunk.content,
                            "id": chunk.name,
                            "metadata": metadata_str,
                        },
                    )
            else:
                # TODO: delete this block when we refactor the trace manager
                for i, chunk in enumerate(chunks):
                    metadata_str = json.dumps(chunk.metadata)
                    span.set_attributes(
                        {
                            f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": chunk.content,
                            f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": chunk.name,
                            f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.metadata": metadata_str,
                        }
                    )
            span.set_status(trace_api.StatusCode.OK)

        return chunks


class DummyRetriever(Retriever):
    def __init__(self, trace_manager: TraceManager, whole_knowledge_base: list[SourceChunk]):
        self.trace_manager = trace_manager
        self._whole_knowledge_base = whole_knowledge_base

    def _get_chunks_without_trace(self, query_text: str, filters: Optional[dict] = None) -> list[SourceChunk]:
        return self._whole_knowledge_base
