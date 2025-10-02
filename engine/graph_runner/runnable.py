from typing import Protocol, runtime_checkable, Optional, Dict


from engine.agent.types import ToolDescription, AgentPayload, NodeData


@runtime_checkable
class Runnable(Protocol):
    tool_description: ToolDescription

    async def run(self, *inputs: AgentPayload | NodeData, **kwargs) -> AgentPayload | NodeData:
        """Run the runnable with the given inputs and kwargs."""

    def run_sync(self, *inputs: AgentPayload | NodeData, **kwargs) -> AgentPayload | NodeData:
        """Run the runnable with the given inputs and kwargs synchronously."""

    # Canonical ports accessors for cleaner GraphRunner logic
    @classmethod
    def get_canonical_ports(cls) -> Dict[str, Optional[str]]:
        """Return canonical input/output port names. Defaults to {input: input, output: output}."""
        return {"input": "input", "output": "output"}
