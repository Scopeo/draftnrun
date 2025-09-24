import logging

from typing import Type, Any
from pydantic import BaseModel, Field


from openinference.semconv.trace import OpenInferenceSpanKindValues

from engine.agent.agent import Agent
from engine.agent.types import ToolDescription, ComponentAttributes
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

DEFAULT_STATIC_RESPONDER_TOOL_DESCRIPTION = ToolDescription(
    name="Static_Responder_Tool",
    description="A static responder tool that responds with a static message.",
    tool_properties={},
    required_tool_properties=[],
)


class StaticResponderInputs(BaseModel):
    input: Any = Field(description="Input it's ignored.")


class StaticResponderOutputs(BaseModel):
    input_from_previous: Any = Field(description="Propagated input from the previous node.")
    static_message: str = Field(description="The message that will be returned.")


class StaticResponder(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "input", "output": "static_message"}

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return StaticResponderInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return StaticResponderOutputs

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        static_message: str,
        tool_description: ToolDescription = DEFAULT_STATIC_RESPONDER_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._static_message = static_message

    async def _run_without_io_trace(
        self,
        inputs: StaticResponderInputs,
        ctx: dict,
    ) -> StaticResponderOutputs:

        return StaticResponderOutputs(
            input_from_previous=inputs.input,
            static_message=self._static_message,
        )
