import warnings

from engine.agent.agent import Agent, ToolDescription, AgentPayload, ChatMessage
from engine.trace.trace_manager import TraceManager


class SequentialPipeline(Agent):
    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_instance_name: str,
        agents: list[Agent],
    ) -> None:
        warnings.warn(
            "SequentialPipeline is deprecated and will be removed in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(
            trace_manager,
            tool_description,
            component_instance_name,
        )
        self.agents = agents if isinstance(agents, list) else [agents]

    async def _run_without_trace(self, *inputs: AgentPayload, **kwargs) -> AgentPayload:
        current_agent_input = inputs[0]
        for agent in self.agents:
            agent_output = await agent.run(inputs=current_agent_input)
            current_agent_input = AgentPayload(messages=[ChatMessage(role="user", content=agent_output.message)])

        return AgentPayload(messages=[ChatMessage(role="assistant", content=current_agent_input.messages[-1].content)])
