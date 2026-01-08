import logging
from typing import Any, Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from pydantic import BaseModel, Field

from engine.components.build_context import build_context_from_vocabulary_chunks
from engine.components.component import Component
from engine.components.rag.formatter import Formatter
from engine.components.rag.reranker import Reranker
from engine.components.rag.retriever import Retriever
from engine.components.rag.vocabulary_search import VocabularySearch
from engine.components.synthesizer import Synthesizer
from engine.components.types import ComponentAttributes, ToolDescription
from engine.components.utils import merge_qdrant_filters_with_and_conditions
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

# How we combine multiple filters conditions in Qdrant.
FILTERING_CONDITION_WITH_METADATA_QDRANT = "AND"


class RAGInputs(BaseModel):
    query_text: str = Field(description="The search query for the knowledge base.")
    filters: Optional[dict] = Field(default=None, description="Qdrant filter object.")


class RAGOutputs(BaseModel):
    output: str = Field(description="The synthesized response from the RAG pipeline.")
    is_final: bool = Field(description="Indicates if the response is final and successful.")
    artifacts: dict[str, Any] = Field(description="Artifacts produced by the RAG pipeline, such as sources.")


class RAG(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.CHAIN.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return RAGInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return RAGOutputs

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        retriever: Retriever,
        synthesizer: Synthesizer,
        component_attributes: Optional[ComponentAttributes] = None,
        reranker: Optional["Reranker"] = None,
        formatter: Optional[Formatter] = None,
        vocabulary_search: Optional[VocabularySearch] = None,
        input_data_field_for_messages_history: str = "messages",
    ) -> None:
        if component_attributes is None:
            component_attributes = ComponentAttributes(component_instance_name=self.__class__.__name__)
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._retriever = retriever
        self._synthesizer = synthesizer
        self._reranker = reranker
        if formatter is None:
            formatter = Formatter(add_sources=False)
        self._formatter = formatter
        self._vocabulary_search = vocabulary_search
        self.input_data_field_for_messages_history = input_data_field_for_messages_history

    async def _run_without_io_trace(self, inputs: RAGInputs, ctx: dict) -> RAGOutputs:
        if not inputs.query_text:
            raise ValueError("No query_text provided for the RAG tool.")
        filter_to_process = inputs.filters
        if "rag_filter" in ctx and ctx["rag_filter"]:
            if inputs.filters:
                filter_to_process = merge_qdrant_filters_with_and_conditions(inputs.filters, ctx["rag_filter"])
            else:
                filter_to_process = ctx["rag_filter"]
        chunks = await self._retriever.get_chunks(query_text=inputs.query_text, filters=filter_to_process)

        if self._reranker is not None:
            chunks = await self._reranker.rerank(query=inputs.query_text, chunks=chunks)

        vocabulary_context = {}
        if self._vocabulary_search is not None:
            vocabulary_chunks = self._vocabulary_search.get_chunks(query_text=inputs.query_text)
            vocabulary_context = {
                self._vocabulary_search.vocabulary_context_prompt_key: build_context_from_vocabulary_chunks(
                    vocabulary_chunks=vocabulary_chunks
                )
            }

        sourced_response = await self._synthesizer.get_response(
            query_str=inputs.query_text,
            chunks=chunks,
            optional_contexts=vocabulary_context,
        )

        sourced_response = self._formatter.format(sourced_response)

        for i, source in enumerate(chunks):
            self.log_trace({
                f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": source.content,
                f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": source.name,
            })

        return RAGOutputs(
            output=sourced_response.response,
            is_final=sourced_response.is_successful,
            artifacts={"sources": sourced_response.sources},
        )

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "query_text", "output": "output"}


def format_rag_tool_description(source: str) -> ToolDescription:
    return ToolDescription(
        name="RAG",
        description=(
            "Searches a document database to retrieve relevant information in the "
            f"company's knowledge base {source}.\n\n"
            "OUTPUT FORMAT RULES (read first):\n"
            "• Return a JSON object with keys: `query_text` (string)\n"
        ),
        tool_properties={
            "query_text": {
                "type": "string",
                "description": "The search query for the knowledge base.",
            },
        },
        required_tool_properties=["query_text"],
    )
