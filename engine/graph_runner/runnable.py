from typing import Dict, Optional, Protocol, Type, runtime_checkable

from pydantic import BaseModel

from engine.components.types import AgentPayload, NodeData, ToolDescription


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

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        """Return the input schema for the runnable."""

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        """Return the output schema for the runnable."""
