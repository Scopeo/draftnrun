from typing import Protocol, runtime_checkable


from engine.agent.types import ToolDescription, AgentPayload, NodeData


@runtime_checkable
class Runnable(Protocol):
    tool_description: ToolDescription

    async def run(self, *inputs: AgentPayload | NodeData, **kwargs) -> AgentPayload | NodeData:
        """Run the runnable with the given inputs and kwargs."""

    def run_sync(self, *inputs: AgentPayload | NodeData, **kwargs) -> AgentPayload | NodeData:
        """Run the runnable with the given inputs and kwargs synchronously."""
