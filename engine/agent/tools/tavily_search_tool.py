import logging
import json
from typing import Optional

from tavily import TavilyClient
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.agent import (
    Agent,
    ChatMessage,
    AgentPayload,
    ComponentAttributes,
    ToolDescription,
    SourceChunk,
    SourcedResponse,
)
from engine.agent.synthesizer import Synthesizer
from engine.trace.trace_manager import TraceManager
from engine.llm_services.llm_service import CompletionService
from engine.agent.rag.formatter import Formatter
from settings import settings

LOGGER = logging.getLogger(__name__)

TAVILY_TOOL_DESCRIPTION = ToolDescription(
    name="tavily_api",
    description="Tavily is a search API that provides sources for the input query.",
    tool_properties={
        "query": {"type": "string", "description": "The natural language question to ask the API."},
        "topic": {
            "type": "string",
            "enum": ["general", "news"],
            "description": (
                "The category of the search. This will determine whether to use only recent information (news) "
                " or perform a ordinary web search (general). Default is 'general'"
            ),
        },
        "days": {
            "type": "integer",
            "description": (
                "The number of days back from the current date to include in the search results. "
                "This specifies the time frame of data to be retrieved. Please note that this feature is "
                "only available when using the 'news' search topic."
            ),
        },
        "include_domains": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "A list of domains to include in the search results. This is useful when you want to limit the search "
                "to a specific set of websites."
            ),
        },
    },
    required_tool_properties=["query", "topic"],
)


class TavilyApiTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        completion_service: CompletionService,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = TAVILY_TOOL_DESCRIPTION,
        tavily_api_key: str = settings.TAVILY_API_KEY,
        synthesizer: Optional[Synthesizer] = None,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.trace_manager = trace_manager
        self.tavily_client = TavilyClient(api_key=tavily_api_key)
        if synthesizer is None:
            synthesizer = Synthesizer(completion_service=completion_service, trace_manager=trace_manager)
        self._synthesizer = synthesizer

    def search_results(
        self, query: str, topic: str, days: int = 3, include_domains: Optional[list[str]] = None
    ) -> list[SourceChunk]:
        results = self.tavily_client.search(
            query,
            topic=topic,
            days=days,
            include_domains=include_domains,
        )["results"]
        return [
            SourceChunk(
                name=result["title"],
                document_name=result["title"],
                content=result["content"],
                url=result["url"],
                metadata={
                    "url": result["url"],
                },
            )
            for result in results
        ]

    async def _run_without_trace(
        self,
        *inputs: AgentPayload,
        query: str,
        topic: str,
        days: int = None,
        include_domains: list[str] = None,
    ) -> AgentPayload:
        agent_input = inputs[0]
        if days is None:
            LOGGER.info("No days parameter provided. Defaulting to 3 days.")
            days = 3
        content = query or agent_input.last_message.content
        if content is None:
            raise ValueError("No content provided for the Tavily API tool.")

        sources = self.search_results(query=content, topic=topic, days=days, include_domains=include_domains)

        with self.trace_manager.start_span("TavilyApiSearchResults") as span:
            for i, source in enumerate(sources):
                span.set_attributes(
                    {
                        SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                        f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.content": source.content,
                        f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.id": source.name,
                        f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{i}.document.metadata": json.dumps(source.metadata),
                    }
                )

        response = await self._synthesizer.get_response(
            chunks=sources,
            query_str=str(agent_input.last_message.model_dump(include={"role", "content"})),
        )

        if self._synthesizer.response_format is SourcedResponse:
            response = Formatter(add_sources=True).format(response)
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=response.response)],
                artifacts={"sources": response.sources},
                is_final=response.is_successful,
            )
        else:
            response = Formatter().format(response)
            return AgentPayload(messages=[ChatMessage(role="assistant", content=response.response)])
