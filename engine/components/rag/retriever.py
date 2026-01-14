import json
import logging
from typing import Any, Optional, Type
from uuid import UUID

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from engine.components.build_context import build_context_from_source_chunks
from engine.components.component import Component
from engine.components.synthesizer_prompts import DEFAULT_INSTRUCTIONS_FEW_SHOT_LEARNING
from engine.components.types import ComponentAttributes, SourceChunk, ToolDescription
from engine.components.utils import merge_qdrant_filters_with_and_conditions
from engine.qdrant_service import QdrantService
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager
from ingestion_script.utils import SOURCE_ID_COLUMN_NAME

LOGGER = logging.getLogger(__name__)

RETRIEVER_CITATION_INSTRUCTION = (
    "When using information from retrieved sources, cite them using [1], [2], etc. "
    "Use the retriever tool ONCE, then answer based on the retrieved information. "
    "If the retrieved information is not relevant, say so clearly rather than retrieving again. \n"
    f"{DEFAULT_INSTRUCTIONS_FEW_SHOT_LEARNING}"
)

RETRIEVER_TOOL_DESCRIPTION = ToolDescription(
    name="retriever",
    description="Retrieve relevant document chunks from a knowledge base using semantic search.",
    tool_properties={
        "query": {
            "type": "string",
            "description": "The search query to retrieve relevant chunks from the knowledge base.",
        },
    },
    required_tool_properties=["query"],
)


def cast_string_to_list(string: Optional[str]) -> list[str]:
    """Cast a comma-separated string into a list of trimmed strings."""
    if not string:
        return []
    return [s.strip() for s in string.split(",") if s.strip()]


class RetrieverInputs(BaseModel):
    query: str = Field(
        description="The search query to retrieve relevant chunks from the knowledge base.",
    )
    filters: Optional[dict] = Field(
        default=None,
        description="Optional filters to apply to the retrieval (e.g., metadata filters).",
    )
    model_config = {"extra": "allow"}


class RetrieverOutputs(BaseModel):
    output: str = Field(description="Summary of retrieved chunks.")
    chunks: list[SourceChunk] = Field(description="The retrieved document chunks from the knowledge base.")
    artifacts: dict[str, Any] = Field(
        default_factory=dict,
        description="Artifacts including sources for display in the UI.",
    )


class Retriever(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return RetrieverInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return RetrieverOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "query", "output": "chunks"}

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
        source_id: Optional[UUID] = None,
        tool_description: ToolDescription = RETRIEVER_TOOL_DESCRIPTION,
    ):
        if component_attributes is None:
            component_attributes = ComponentAttributes(component_instance_name=self.__class__.__name__)

        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )

        self.collection_name = collection_name
        self._max_retrieved_chunks = max_retrieved_chunks
        self._vectorestore_service = qdrant_service
        self.enable_chunk_penalization = enable_date_penalty_for_chunks
        self.chunk_age_penalty_rate = chunk_age_penalty_rate
        self.default_penalty_rate = default_penalty_rate
        self.metadata_date_key = metadata_date_key
        self.max_retrieved_chunks_after_penalty = max_retrieved_chunks_after_penalty
        self.source_id = source_id
        LOGGER.info(f"Retriever initialized with source_id={self.source_id} for collection={collection_name}")

    async def _get_chunks_without_trace(
        self,
        query_text: str,
        filters: Optional[dict] = None,
    ) -> list[SourceChunk]:
        source_id_filter = None
        if self.source_id:
            source_id_filter = {"must": [{"key": SOURCE_ID_COLUMN_NAME, "match": {"value": str(self.source_id)}}]}

        final_filter = (
            merge_qdrant_filters_with_and_conditions(source_id_filter, filters)
            if (source_id_filter and filters)
            else (source_id_filter or filters)
        )
        LOGGER.info(
            f"Retriever querying collection '{self.collection_name}' with source_id={self.source_id}, "
            f"filter: {json.dumps(final_filter)}"
        )
        chunks = await self._vectorestore_service.retrieve_similar_chunks_async(
            query_text=query_text,
            collection_name=self.collection_name,
            limit=self._max_retrieved_chunks,
            filter=final_filter,
            enable_date_penalty_for_chunks=self.enable_chunk_penalization,
            chunk_age_penalty_rate=self.chunk_age_penalty_rate,
            default_penalty_rate=self.default_penalty_rate,
            metadata_date_key=cast_string_to_list(self.metadata_date_key),
            max_retrieved_chunks_after_penalty=self.max_retrieved_chunks_after_penalty,
        )
        LOGGER.info(
            f"Retriever retrieved {len(chunks)} chunks from collection "
            f"'{self.collection_name}' with source_id={self.source_id}"
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
            input_data = {"Query": query_text, "Filter": filters}
            span.set_attributes({
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                SpanAttributes.EMBEDDING_MODEL_NAME: self._vectorestore_service._embedding_service._model_name,
                SpanAttributes.INPUT_VALUE: serialize_to_json(input_data, shorten_string=False),
                "component_instance_id": (
                    str(self.component_attributes.component_instance_id)
                    if self.component_attributes.component_instance_id is not None
                    else None
                ),
                "source_id": str(self.source_id),
            })

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
                    span.set_attributes({
                        f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": chunk.content,
                        f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": chunk.name,
                        f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.metadata": metadata_str,
                    })
            span.set_status(trace_api.StatusCode.OK)

        return chunks

    async def _run_without_io_trace(
        self,
        inputs: RetrieverInputs,
        ctx: dict,
    ) -> RetrieverOutputs:
        """Tool interface for agent use - wraps get_chunks with proper formatting."""
        query_str = inputs.query
        if not query_str:
            raise ValueError("No query provided for the retriever tool.")

        span = get_current_span()
        trace_input = {"query": query_str, "filters": inputs.filters}
        span.set_attributes({
            SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
            SpanAttributes.INPUT_VALUE: serialize_to_json(trace_input, shorten_string=False),
        })

        chunks = await self.get_chunks(
            query_text=query_str,
            filters=inputs.filters,
        )
        tool_name = (
            self.component_attributes.component_instance_name
            if self.component_attributes and self.component_attributes.component_instance_name
            else "retriever"
        )
        for chunk in chunks:
            chunk.tool_name = tool_name

        for i, chunk in enumerate(chunks):
            metadata_str = json.dumps(chunk.metadata)
            span.set_attributes({
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": chunk.content,
                f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": chunk.name,
                f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.metadata": metadata_str,
                f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.tool_name": tool_name,
            })

        chunks_output = build_context_from_source_chunks(
            sources=chunks,
            llm_metadata_keys=chunks[0].metadata.keys() if chunks else [],
        )

        return RetrieverOutputs(output=chunks_output, chunks=chunks, artifacts={"sources": chunks})


class DummyRetriever(Retriever):
    def __init__(self, trace_manager: TraceManager, whole_knowledge_base: list[SourceChunk]):
        self.trace_manager = trace_manager
        self._whole_knowledge_base = whole_knowledge_base

    def _get_chunks_without_trace(self, query_text: str, filters: Optional[dict] = None) -> list[SourceChunk]:
        return self._whole_knowledge_base
