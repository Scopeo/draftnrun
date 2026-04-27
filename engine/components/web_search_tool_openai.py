import json
from typing import Callable, Optional, Type
from uuid import UUID

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from ada_backend.database.models import ParameterType
from engine.components.component import Component
from engine.components.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.constants import DEFAULT_MODEL_WEB_SEARCH
from engine.llm_services.llm_service import WebSearchService
from engine.llm_services.utils import get_llm_provider_and_model
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
    completion_model: str = Field(
        default=DEFAULT_MODEL_WEB_SEARCH,
        json_schema_extra={
            "is_tool_input": False,
            "parameter_type": ParameterType.LLM_MODEL,
            "ui_component": "Select",
            "ui_component_properties": {"label": "Model Name", "model_capabilities": ["web_search"]},
        },
    )
    query: Optional[str] = Field(
        default=None,
        description="The standalone question to be answered using web search.",
        json_schema_extra={
            "is_tool_input": True,
        },
    )
    messages: Optional[list[ChatMessage]] = Field(default=None, description="Optional legacy message context.")
    filters: Optional[SearchFilters] = Field(
        default=None,
        description="Optional filters to restrict search results",
        json_schema_extra={
            "is_tool_input": True,
        },
    )
    model_config = {"extra": "allow"}


class WebSearchOpenAIToolOutputs(BaseModel):
    output: str = Field(description="The result from the web search.")


class WebSearchOpenAITool(Component):
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
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        llm_api_key: Optional[str] = None,
        model_id_resolver: Optional[Callable[[str], Optional[UUID]]] = None,
        tool_description: ToolDescription = DEFAULT_WEB_SEARCH_OPENAI_TOOL_DESCRIPTION,
        allowed_domains: Optional[list[str]] = None,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._llm_api_key = llm_api_key
        self._model_id_resolver = model_id_resolver or (lambda _: None)
        self._allowed_domains = allowed_domains

    async def _run_without_io_trace(self, inputs: WebSearchOpenAIToolInputs, ctx: dict) -> WebSearchOpenAIToolOutputs:
        provider, model_name = get_llm_provider_and_model(inputs.completion_model)
        web_service = WebSearchService(
            trace_manager=self.trace_manager,
            provider=provider,
            model_name=model_name,
            api_key=self._llm_api_key,
            model_id=self._model_id_resolver(model_name),
        )

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
            SpanAttributes.LLM_MODEL_NAME: web_service._model_name,
            "model_id": str(web_service._model_id) if web_service._model_id is not None else None,
        })
        output = await web_service.web_search_async(query_str, final_allowed_domains)
        return WebSearchOpenAIToolOutputs(output=output)
