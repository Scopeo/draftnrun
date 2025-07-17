from typing import Protocol, runtime_checkable


from engine.agent.data_structures import ToolDescription, AgentPayload


@runtime_checkable
class Runnable(Protocol):
    tool_description: ToolDescription

    async def run(self, *inputs: AgentPayload, **kwargs) -> AgentPayload:
        """Run the runnable with the given inputs and kwargs."""

    def run_sync(self, *inputs: AgentPayload, **kwargs) -> AgentPayload:
        """Run the runnable with the given inputs and kwargs synchronously."""
