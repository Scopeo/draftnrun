from typing import Optional

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent
from engine.agent.types import AgentPayload, ChatMessage, ToolDescription, ComponentAttributes
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


class WebSearchOpenAITool(Agent):
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

    async def _run_without_io_trace(
        self,
        *inputs: AgentPayload,
        query: Optional[str] = None,
    ) -> AgentPayload:
        agent_input = inputs[0]
        query_str = query or agent_input.last_message.content
        span = get_current_span()
        span.set_attributes(
            {
                SpanAttributes.INPUT_VALUE: query_str,
                SpanAttributes.LLM_MODEL_NAME: self._web_service._model_name,
            }
        )
        output = await self._web_service.web_search_async(query_str)
        return AgentPayload(messages=[ChatMessage(role="assistant", content=output)])
