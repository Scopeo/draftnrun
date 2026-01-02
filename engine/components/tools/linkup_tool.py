import json
from datetime import date
from typing import Optional

from linkup import LinkupClient
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span

from engine.components.component import Component
from engine.components.types import (
    AgentPayload,
    ChatMessage,
    ComponentAttributes,
    SourceChunk,
    SourcedResponse,
    ToolDescription,
)
from engine.trace.trace_manager import TraceManager
from settings import settings

LINKUP_TOOL_DESCRIPTION = ToolDescription(
    name="Linkup_Web_Search_Tool",
    description="Answer a question using Linkup web search.",
    tool_properties={
        "query": {
            "type": "string",
            "description": "The standalone question to be answered using web search.",
        },
        "from_date": {
            "type": "string",
            "description": "The date from which the search results should be considered, "
            "in ISO 8601 format (YYYY-MM-DD).",
        },
        "to_date": {
            "type": "string",
            "description": "The date until which the search results should be considered, "
            "in ISO 8601 format (YYYY-MM-DD).",
        },
        "include_domains": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The domains you want to search on. By default, don't restrict the search.",
        },
        "exclude_domains": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The domains you want to exclude of the search. By default, don't restrict the search.",
        },
        "depth": {
            "type": "string",
            "description": "The depth format is standard or deep. "
            "standard: Returns results faster, suitable for low-latency scenarios. "
            "deep: Takes longer but yields more comprehensive results.",
        },
    },
    required_tool_properties=["query", "depth"],
)


class LinkupSearchTool(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = LINKUP_TOOL_DESCRIPTION,
        linkup_api_key: str = settings.LINKUP_API_KEY,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.trace_manager = trace_manager
        self.linkup_client = LinkupClient(api_key=linkup_api_key)

    def search_results(
        self,
        query: str,
        depth: str,
        output_type: str,
        exclude_domains: Optional[list[str]] = None,
        include_domains: Optional[list[str]] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> SourcedResponse:
        response = self.linkup_client.search(
            query,
            depth=depth,
            output_type=output_type,
            exclude_domains=exclude_domains,
            include_domains=include_domains,
            from_date=date.fromisoformat(from_date) if from_date else None,
            to_date=date.fromisoformat(to_date) if to_date else None,
        )
        answer = response.answer
        sources = response.sources
        source_chunks = [
            SourceChunk(
                name=source.name,
                document_name=source.name,
                content=source.snippet,
                url=source.url,
                metadata={
                    "url": source.url,
                },
            )
            for source in sources
        ]
        return SourcedResponse(response=answer, sources=source_chunks, is_successful=True)

    async def _run_without_io_trace(
        self,
        *inputs: AgentPayload,
        query: str,
        depth: str,
        output_type: str = "sourcedAnswer",
        exclude_domains: Optional[list[str]] = None,
        include_domains: Optional[list[str]] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        ctx: Optional[dict] = None,
    ) -> AgentPayload:
        agent_input = inputs[0]
        content = query or agent_input.last_message.content
        if content is None:
            raise ValueError("No content provided for the Linkup search tool.")
        span = get_current_span()
        trace_input = (
            f"query: {query}\n"
            f"from date: {from_date}\n"
            f"to date: {to_date}\n"
            f"include domains: {include_domains}\n"
            f"exclude domains: {exclude_domains}\n"
            f"depth: {depth}"
        )
        span.set_attributes(
            {
                SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                SpanAttributes.INPUT_VALUE: trace_input,
            }
        )
        response = self.search_results(
            query=content,
            depth=depth,
            output_type=output_type,
            exclude_domains=exclude_domains,
            include_domains=include_domains,
            from_date=from_date,
            to_date=to_date,
        )

        for i, source in enumerate(response.sources):
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": source.content,
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": source.name,
                    f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.metadata": json.dumps(source.metadata),
                }
            )

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=response.response)],
            artifacts={"sources": response.sources},
            is_final=response.is_successful,
        )
