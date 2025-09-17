
from datetime import date
from typing import Union
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import Agent, AgentPayload, ComponentAttributes, ToolDescription
from engine.agent.types import ChatMessage, SourceChunk, SourcedResponse
from engine.trace.trace_manager import TraceManager
from engine.agent.rag.formatter import Formatter

from linkup import LinkupClient
import json

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
            "description": "Filter results from a specific date (format: YYYY-MM-DD)"
        },
        "to_date": {
            "type": "string",
            "description": "Filter results until a specific date (format: YYYY-MM-DD)"
        },
        "include_domains": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Filter results to only include specific domains"
        },
        "exclude_domains": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Filter results to exclude specific domains"
        }
    },
    required_tool_properties=["query"],
)

class LinkupSearchTool(Agent):
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
        self.trace_manager=trace_manager
        self.linkup_client=LinkupClient(api_key=linkup_api_key)

    def search_results(
        self,
        query: str,
        depth: str,
        output_type: str,
        exclude_domains: Union[list[str], None],
        include_domains: Union[list[str], None],
        from_date: Union[date, None],
        to_date: Union[date, None],
    ) -> SourcedResponse:
        response=self.linkup_client.search(
            query,
            depth=depth,
            output_type=output_type,
            exclude_domains=exclude_domains,
            include_domains=include_domains,
            from_date=from_date,
            to_date=to_date,
        )
        answer=response.answer
        sources=response.sources
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
        depth: str = "standard",
        output_type: str = "sourcedAnswer",
        exclude_domains: Union[list[str], None] = None,
        include_domains: Union[list[str], None] = None,
        from_date: Union[date, None] = None,
        to_date: Union[date, None] = None,
    ) -> AgentPayload:
        agent_input = inputs[0]
        content = query or agent_input.last_message.content
        if content is None:
            raise ValueError("No content provided for the Linkup search tool.")

        response = self.search_results(query=content,
                                       depth=depth,
                                       output_type=output_type,
                                       exclude_domains=exclude_domains,
                                       include_domains=include_domains,
                                       from_date=from_date,
                                       to_date=to_date)

        with self.trace_manager.start_span("LinkupSearchResults") as span:
            for i, source in enumerate(response.sources):
                span.set_attributes(
                    {
                        SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                        f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": source.content,
                        f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": source.name,
                        f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.metadata": json.dumps(source.metadata),
                    }
                )

        response = Formatter(add_sources=True).format(response)
        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=response.response)],
            artifacts={"sources": response.sources},
            is_final=response.is_successful,
        )
