from typing import Optional, Type
from pydantic import BaseModel, Field

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent
from engine.agent.types import ToolDescription, ComponentAttributes, ChatMessage
from engine.llm_services.llm_service import WebSearchService
from engine.trace.trace_manager import TraceManager


DEFAULT_WEB_SEARCH_OPENAI_TOOL_DESCRIPTION = ToolDescription(
    name="Web_Search_Tool",
    description="Answer a question using web search.",
    tool_properties={
        "query": {
            "type": "string",
            "description": "The standalone question to be answered using web search.",
        },
    },
    required_tool_properties=["query"],
)


class WebSearchOpenAIToolInputs(BaseModel):
    query: Optional[str] = Field(default=None, description="The standalone question to be answered using web search.")
    messages: Optional[list[ChatMessage]] = Field(default=None, description="Optional legacy message context.")
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
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._web_service = web_service

    async def _run_without_io_trace(self, inputs: WebSearchOpenAIToolInputs, ctx: dict) -> WebSearchOpenAIToolOutputs:
        # Preserve previous behavior: prefer explicit query, else last user message content
        query_str = inputs.query
        if not query_str and inputs.messages:
            last = inputs.messages[-1]
            query_str = last.content if last and last.role == "user" else None
        if not query_str:
            query_str = ""

        span = get_current_span()
        span.set_attributes(
            {
                SpanAttributes.INPUT_VALUE: query_str,
                SpanAttributes.LLM_MODEL_NAME: self._web_service._model_name,
            }
        )
        output = await self._web_service.web_search_async(query_str)
        return WebSearchOpenAIToolOutputs(output=output)
