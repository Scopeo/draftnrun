from typing import Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import (
    AgentPayload,
    ChatMessage,
    ToolDescription,
)
from engine.agent.rag.rag import RAG
from engine.agent.rag.reranker import Reranker
from engine.agent.rag.retriever import Retriever
from engine.agent.rag.vocabulary_search import VocabularySearch
from engine.trace.trace_manager import TraceManager
from engine.agent.vocabulary_enhanced_synthesizer import VocabularyEnhancedSynthesizer
from engine.agent.utils import format_qdrant_filter
from engine.agent.rag.formatter import Formatter


class VocabularyEnhancedRAG(RAG):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.CHAIN.value
    """
    This is an image-capable RAG that takes an image and text as inputs
    and returns a response that may include relevant image IDs.
    """

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        retriever: Retriever,
        synthesizer: VocabularyEnhancedSynthesizer,
        vocabulary_search: VocabularySearch,
        component_instance_name: str = "RAG with Vocabulary Search",
        reranker: Optional[Reranker] = None,
        filtering_condition: str = "OR",
        formatter: Optional[Formatter] = None,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            synthesizer=synthesizer,
            retriever=retriever,
            reranker=reranker,
            component_instance_name=component_instance_name,
        )
        self._synthesizer = synthesizer
        self._vocabulary_search = vocabulary_search
        self._filtering_condition = filtering_condition
        self._formatter = formatter

    async def _run_without_trace(
        self,
        agent_input: AgentPayload,
        query_text: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> AgentPayload:
        content = query_text or agent_input.last_message.content
        if content is None:
            raise ValueError("No content provided for the RAG tool.")
        formatted_filters = format_qdrant_filter(filters, self._filtering_condition)
        chunks = self._retriever.get_chunks(query_text=content, filters=formatted_filters)
        vocabulary_chunks = self._vocabulary_search.get_chunks(query_text=content)

        if self._reranker is not None:
            chunks = self._reranker.rerank(query=content, chunks=chunks)

        sourced_response = self._synthesizer.get_response(
            vocabulary_chunks=vocabulary_chunks,
            chunks=chunks,
            query_str=content,
        )
        if self._formatter is not None:
            sourced_response = self._formatter.format(sourced_response)

        for i, source in enumerate(chunks):
            self.log_trace(
                {
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": source.content,
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": source.name,
                }
            )

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=sourced_response.response)],
            is_final=sourced_response.is_successful,
            artifacts={"sources": sourced_response.sources},
        )
