import logging
from typing import Type

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from pydantic import BaseModel

from engine.agent.types import ToolDescription, ComponentAttributes, AgentPayload, NodeData
from engine.trace.trace_manager import TraceManager
from engine.agent.utils import load_str_to_json
from engine.trace.serializer import serialize_to_json

LOGGER = logging.getLogger(__name__)

DEFAULT_INPUT_TOOL_DESCRIPTION = ToolDescription(
    name="Input_Tool",
    description=("An input tool that filters the input data to return an AgentPayload."),
    tool_properties={
        "input_data": {
            "type": "json",
            "description": "An input tool",
        },
    },
    required_tool_properties=[],
)


class Input:
    # LEGACY: Mark as unmigrated for retro-compatibility
    # TODO: Remove after migration to Agent base class
    migrated: bool = False

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        payload_schema: str,
    ):
        self.trace_manager = trace_manager
        self.tool_description = tool_description
        self.component_attributes = component_attributes
        self.payload_schema = load_str_to_json(payload_schema)

    def get_canonical_ports(self) -> dict[str, str | None]:
        # Expose the canonical output as the messages list so default mappings
        # can auto-wire to downstream components expecting chat messages.
        return {"output": "messages"}

    # LEGACY: Schema methods for retro-compatibility with type discovery
    # TODO: Remove after migration to Agent base class
    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        """Input component accepts any input data."""
        from engine.legacy_compatibility import create_legacy_input_schema

        return create_legacy_input_schema()

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        """Input component outputs messages list (canonical port)."""
        from engine.legacy_compatibility import create_legacy_input_output_schema

        return create_legacy_input_output_schema()

    # TODO: Refactor Agent I/O to use an unified input/output object:
    async def run(self, input_data: AgentPayload | dict | NodeData) -> dict:
        # Normalize input to a plain dict
        # TODO: Remove after I/O refactor migration
        if isinstance(input_data, NodeData):
            base: dict = dict(input_data.data or {})

        elif isinstance(input_data, AgentPayload):
            base = input_data.model_dump()
        else:
            base = dict(input_data)

        filtered_input = base.copy()
        for k, v in self.payload_schema.items():
            if k not in filtered_input:
                filtered_input[k] = v

        with self.trace_manager.start_span(self.component_attributes.component_instance_name) as span:
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.UNKNOWN.value,
                    SpanAttributes.INPUT_VALUE: serialize_to_json(base, shorten_string=True),
                    SpanAttributes.OUTPUT_VALUE: serialize_to_json(filtered_input, shorten_string=True),
                    "component_instance_id": str(self.component_attributes.component_instance_id),
                }
            )
            span.set_status(trace_api.StatusCode.OK)

        # Return the canonical output format based on canonical ports
        canonical_ports = self.get_canonical_ports()
        if canonical_ports.get("output") == "messages" and "messages" in filtered_input:
            messages = filtered_input["messages"]
            # Input component outputs list[dict] as declared in legacy schema
            return {"messages": messages}

        return filtered_input
