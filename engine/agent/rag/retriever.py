from typing import Optional
from datetime import datetime
import json

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import SourceChunk
from engine.qdrant_service import QdrantService
from engine.trace.trace_manager import TraceManager


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

    def _get_chunks_without_trace(
        self,
        query_text: str,
        filters: Optional[dict] = None,
    ) -> list[SourceChunk]:
        chunks = self._vectorestore_service.retrieve_similar_chunks(
            query_text=query_text,
            collection_name=self.collection_name,
            limit=self._max_retrieved_chunks,
            filter=filters,
        )
        if self.enable_chunk_penalization:
            chunks = self.apply_date_penalty_to_chunks(chunks)

        return chunks

    @staticmethod
    def calculate_age_penalty(
        chunk: SourceChunk,
        age_penalty_rate: float,
        metadata_date_key: str,
        default_age_penalty_rate: float,
    ) -> float:
        current_year = datetime.today().year
        start_of_year = datetime(current_year, 1, 1)

        date = chunk.metadata.get(metadata_date_key)
        if not date:
            return default_age_penalty_rate
        chunk_date = datetime.strptime(date.strip(), "%Y-%m-%d")
        age = max(0, (start_of_year - chunk_date).days / 365)
        return min(age * age_penalty_rate, 5 * age_penalty_rate)

    def apply_date_penalty_to_chunks(
        self,
        chunks: list[SourceChunk],
    ) -> list[SourceChunk]:
        for chunk in chunks:
            original_score = chunk.metadata.get("similarity_score", 0)
            penalty = self.calculate_age_penalty(
                chunk,
                self.chunk_age_penalty_rate,
                self.metadata_date_key,
                self.default_penalty_rate,
            )
            chunk.metadata["penalty_score"] = original_score - penalty
        sorted_chunks = sorted(chunks, key=lambda x: x.metadata["penalty_score"], reverse=True)

        return sorted_chunks[: self.max_retrieved_chunks_after_penalty]

    def get_chunks(
        self,
        query_text: str,
        filters: Optional[dict] = None,
    ) -> list[SourceChunk]:
        with self.trace_manager.start_span(self.__class__.__name__) as span:
            chunks = self._get_chunks_without_trace(
                query_text,
                filters,
            )
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                    SpanAttributes.EMBEDDING_MODEL_NAME: self._vectorestore_service._embedding_service._model_name,
                    SpanAttributes.INPUT_VALUE: query_text,
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
