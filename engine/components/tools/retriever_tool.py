import json
from typing import Any, Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from engine.components.build_context import build_context_from_source_chunks
from engine.components.component import Component
from engine.components.rag.retriever import Retriever
from engine.components.types import ComponentAttributes, SourceChunk, ToolDescription
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

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


class RetrieverToolInputs(BaseModel):
    query: str = Field(
        description="The search query to retrieve relevant chunks from the knowledge base.",
    )
    filters: Optional[dict] = Field(
        default=None,
        description="Optional filters to apply to the retrieval (e.g., metadata filters).",
    )
    model_config = {"extra": "allow"}


class RetrieverToolOutputs(BaseModel):
    output: str = Field(description="Summary of retrieved chunks.")
    chunks: list[SourceChunk] = Field(description="The retrieved document chunks from the knowledge base.")
    # TODO: Flatten this dict for easier output consumption
    artifacts: dict[str, Any] = Field(
        default_factory=dict,
        description="Artifacts including sources for display in the UI.",
    )


class RetrieverTool(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return RetrieverToolInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return RetrieverToolOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "query", "output": "chunks"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        retriever: Retriever,
        tool_description: ToolDescription = RETRIEVER_TOOL_DESCRIPTION,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.retriever = retriever

    async def _run_without_io_trace(
        self,
        inputs: RetrieverToolInputs,
        ctx: dict,
    ) -> RetrieverToolOutputs:
        query_str = inputs.query
        if not query_str:
            raise ValueError("No query provided for the retriever tool.")

        span = get_current_span()
        trace_input = {"query": query_str, "filters": inputs.filters}
        span.set_attributes({
            SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
            SpanAttributes.INPUT_VALUE: serialize_to_json(trace_input, shorten_string=False),
        })

        chunks = await self.retriever.get_chunks(
            query_text=query_str,
            filters=inputs.filters,
        )

        tool_name = (
            self.component_attributes.component_instance_name
            if self.component_attributes and self.component_attributes.component_instance_name
            else "retriever"
        )
        for chunk in chunks:
            chunk.metadata["tool_name"] = tool_name

        for i, chunk in enumerate(chunks):
            metadata_str = json.dumps(chunk.metadata)
            span.set_attributes({
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": chunk.content,
                f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": chunk.name,
                f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.metadata": metadata_str,
            })

        chunks_output = build_context_from_source_chunks(
            sources=chunks,
            llm_metadata_keys=chunks[0].metadata.keys() if chunks else [],
        )

        return RetrieverToolOutputs(output=chunks_output, chunks=chunks, artifacts={"sources": chunks})
