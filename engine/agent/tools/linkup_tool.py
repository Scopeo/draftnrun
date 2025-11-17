from datetime import date
from enum import Enum
from typing import Optional, Type
from pydantic import BaseModel, Field
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent
from engine.agent.types import ComponentAttributes, ToolDescription
from engine.agent.types import SourceChunk, SourcedResponse
from engine.trace.trace_manager import TraceManager

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


class LinkupDepth(str, Enum):
    STANDARD = "standard"
    DEEP = "deep"


class LinkupSearchToolInputs(BaseModel):
    query: Optional[str] = Field(
        default=None,
        description="The standalone question to be answered using web search.",
    )
    depth: LinkupDepth = Field(
        default=LinkupDepth.STANDARD,
        description="The depth format: 'standard' or 'deep'",
    )
    from_date: Optional[date] = Field(
        default=None,
        description="The date from which the search results should be considered.",
    )
    to_date: Optional[date] = Field(
        default=None,
        description="The date until which the search results should be considered.",
    )
    include_domains: Optional[list[str]] = Field(
        default=None,
        description="The domains you want to search on.",
    )
    exclude_domains: Optional[list[str]] = Field(
        default=None,
        description="The domains you want to exclude from the search.",
    )
    model_config = {"extra": "allow"}  # For backward compatibility


class LinkupSearchToolOutputs(BaseModel):
    output: str = Field(description="The answer from the Linkup web search.")
    sources: list[SourceChunk] = Field(description="The sources from the Linkup web search.")


class LinkupSearchTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return LinkupSearchToolInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return LinkupSearchToolOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "query", "output": "output"}

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
        depth: LinkupDepth,
        output_type: str,
        exclude_domains: Optional[list[str]] = None,
        include_domains: Optional[list[str]] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> SourcedResponse:
        response = self.linkup_client.search(
            query,
            depth=depth.value,
            output_type=output_type,
            exclude_domains=exclude_domains,
            include_domains=include_domains,
            from_date=from_date,
            to_date=to_date,
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
        inputs: LinkupSearchToolInputs,
        ctx: dict,
    ) -> LinkupSearchToolOutputs:
        query_str = inputs.query
        if not query_str:
            raise ValueError("No content provided for the Linkup search tool.")

        span = get_current_span()
        trace_input = (
            f"query: {query_str}\n"
            f"from date: {inputs.from_date.isoformat() if inputs.from_date else None}\n"
            f"to date: {inputs.to_date.isoformat() if inputs.to_date else None}\n"
            f"include domains: {inputs.include_domains}\n"
            f"exclude domains: {inputs.exclude_domains}\n"
            f"depth: {inputs.depth}"
        )
        span.set_attributes(
            {
                SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                SpanAttributes.INPUT_VALUE: trace_input,
            }
        )

        response = self.search_results(
            query=query_str,
            depth=inputs.depth,
            output_type="sourcedAnswer",
            exclude_domains=inputs.exclude_domains,
            include_domains=inputs.include_domains,
            from_date=inputs.from_date,
            to_date=inputs.to_date,
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

        return LinkupSearchToolOutputs(
            output=response.response,
            sources=response.sources,
        )
