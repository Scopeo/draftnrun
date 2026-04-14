"""
Reusable dummy agent for testing purposes.
This agent simply adds a prefix to input messages, useful for testing graph flows.
"""

import uuid
from typing import Optional

from pydantic import BaseModel

from engine.components.component import Component
from engine.components.types import ChatMessage, ComponentAttributes, ToolDescription


class DummyAgent(Component):
    """A reusable dummy agent for testing that adds a prefix to the input message."""

    migrated = True

    class Inputs(BaseModel):
        messages: Optional[list[ChatMessage]] = None

    class Outputs(BaseModel):
        output: str

    @classmethod
    def get_inputs_schema(cls):
        return cls.Inputs

    @classmethod
    def get_outputs_schema(cls):
        return cls.Outputs

    def __init__(self, trace_manager, prefix: str, agent_id: str = None):
        if agent_id is None:
            agent_id = prefix.lower()

        tool_description = ToolDescription(
            name=f"Dummy Agent {prefix}",
            description=f"Adds '{prefix}' prefix to messages",
            tool_properties={},
            required_tool_properties=[],
        )
        component_attributes = ComponentAttributes(
            component_instance_id=uuid.uuid4(),
            component_instance_name=f"dummy_{prefix}_{agent_id}",
        )
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.prefix = prefix

    async def _run_without_io_trace(self, inputs: Inputs, ctx: dict) -> Outputs:
        if inputs.messages:
            last_content = inputs.messages[-1].content or ""
        else:
            last_content = "empty input"
        return self.Outputs(output=f"[{self.prefix}] {last_content}")
