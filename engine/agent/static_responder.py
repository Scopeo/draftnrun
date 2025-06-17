from engine.agent.agent import Agent, ChatMessage, AgentPayload, ToolDescription
from engine.trace.trace_manager import TraceManager

STATIC_TOOL_DESCRIPTION = ToolDescription(
    name="static_responder",
    description="A tool that responds with a static message.",
    tool_properties={},
    required_tool_properties=[],
)


class StaticResponder(Agent):
    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_instance_name: str,
        response: str,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_instance_name=component_instance_name,
        )
        self.response = response

    async def _run_without_trace(self, *inputs: AgentPayload, **kwargs) -> AgentPayload:
        agent_response = AgentPayload(messages=[ChatMessage(role="system", content=self.response)], is_final=True)
        return agent_response
