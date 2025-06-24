import logging
from typing import Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import (
    Agent,
    ChatMessage,
    AgentPayload,
    ToolDescription,
)
from engine.agent.rag.reranker import Reranker
from engine.agent.rag.retriever import Retriever
from engine.trace.trace_manager import TraceManager
from engine.agent.synthesizer import Synthesizer
from engine.agent.utils import format_qdrant_filter
from engine.agent.rag.formatter import Formatter

LOGGER = logging.getLogger(__name__)


class RAG(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.CHAIN.value

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        retriever: Retriever,
        synthesizer: Synthesizer,
        component_instance_name: str = "RAG",
        reranker: Optional["Reranker"] = None,
        filtering_condition: str = "OR",
        formatter: Optional[Formatter] = None,
        input_data_field_for_messages_history: str = "messages",
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_instance_name=component_instance_name,
        )
        self._retriever = retriever
        self._synthesizer = synthesizer
        self._reranker = reranker
        self._filtering_condition = filtering_condition
        if formatter is None:
            formatter = Formatter(add_sources=False)
        self._formatter = formatter
        self.input_data_field_for_messages_history = input_data_field_for_messages_history

    async def _run_without_trace(
        self,
        *inputs: dict | AgentPayload,
        query_text: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> AgentPayload:
        agent_input = inputs[0]
        if not isinstance(agent_input, AgentPayload):
            # TODO : Will be suppressed when AgentPayload will be suppressed
            agent_input["messages"] = agent_input[self.input_data_field_for_messages_history]
            agent_input = AgentPayload(**agent_input)
        content = query_text or agent_input.last_message.content
        if content is None:
            raise ValueError("No content provided for the RAG tool.")
        formatted_filters = format_qdrant_filter(filters, self._filtering_condition)
        chunks = await self._retriever.get_chunks(query_text=content, filters=formatted_filters)

        if self._reranker is not None:
            chunks = await self._reranker.rerank(query=content, chunks=chunks)

        sourced_response = await self._synthesizer.get_response(
            query_str=content,
            chunks=chunks,
        )

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


def format_rag_tool_description(source: str) -> ToolDescription:
    return ToolDescription(
        name=f"{source}_RAG",
        description=(
            f"Searches a document database to retrieve relevant information in the "
            f"company's knowledge base {source}."
        ),
        tool_properties={
            "query_text": {
                "type": "string",
                "description": "The search query for the knowledge base.",
            },
            # TODO: Improve filter support: https://api.qdrant.tech/api-reference/search/points
            "filters": {
                "type": "object",
                "description": "The filters to apply to the search query.",
            },
        },
        required_tool_properties=[],
    )
