import json
from typing import Optional, Type

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from engine.agent.agent import Agent
from engine.agent.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.llm_services.llm_service import WebSearchService
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

DEFAULT_WEB_SEARCH_OPENAI_TOOL_DESCRIPTION = ToolDescription(
    name="Web_Search_Tool",
    description="Answer a question using web search.",
    tool_properties={
        "query": {
            "type": "string",
            "description": "The standalone question to be answered using web search.",
        },
        "filters": {
            "type": "object",
            "description": (
                "Optional filters to restrict search results. "
                "Can include 'allowed_domains' to limit search to specific domains."
            ),
            "properties": {
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of domains to restrict search results to (e.g., ['mydomain.net', 'myotherdomain.com'])."
                    ),
                }
            },
        },
    },
    required_tool_properties=["query"],
)


class SearchFilters(BaseModel):
    allowed_domains: Optional[list[str]] = Field(
        default=None, description="List of domains to restrict search results to"
    )


class WebSearchOpenAIToolInputs(BaseModel):
    query: Optional[str] = Field(default=None, description="The standalone question to be answered using web search.")
    messages: Optional[list[ChatMessage]] = Field(default=None, description="Optional legacy message context.")
    filters: Optional[SearchFilters] = Field(default=None, description="Optional filters to restrict search results")
    model_config = {"extra": "allow"}


class WebSearchOpenAIToolOutputs(BaseModel):
    output: str = Field(description="The result from the web search.")


class WebSearchOpenAITool(Agent):
    migrated = True

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "query", "output": "output"}

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return WebSearchOpenAIToolInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return WebSearchOpenAIToolOutputs

    def __init__(
        self,
        web_service: WebSearchService,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        tool_description: ToolDescription = DEFAULT_WEB_SEARCH_OPENAI_TOOL_DESCRIPTION,
        allowed_domains: Optional[list[str]] = None,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._web_service = web_service
        self._allowed_domains = allowed_domains

    async def _run_without_io_trace(self, inputs: WebSearchOpenAIToolInputs, ctx: dict) -> WebSearchOpenAIToolOutputs:
        # Preserve previous behavior: prefer explicit query, else last user message content
        query_str = inputs.query
        if not query_str and inputs.messages:
            last = inputs.messages[-1]
            query_str = last.content if last and last.role == "user" else None
        if not query_str:
            query_str = ""

        final_allowed_domains = None
        if self._allowed_domains is not None:
            final_allowed_domains = json.loads(self._allowed_domains)
        elif inputs.filters and inputs.filters.allowed_domains:
            final_allowed_domains = inputs.filters.allowed_domains

        span = get_current_span()
        span.set_attributes({
            SpanAttributes.INPUT_VALUE: serialize_to_json(
                {"query": query_str, "allowed_domains": final_allowed_domains}, shorten_string=True
            ),
            SpanAttributes.LLM_MODEL_NAME: self._web_service._model_name,
            "model_id": str(self._web_service._model_id) if self._web_service._model_id is not None else None,
        })
        output = await self._web_service.web_search_async(query_str, final_allowed_domains)
        return WebSearchOpenAIToolOutputs(output=output)
