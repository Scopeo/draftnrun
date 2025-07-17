import json
import logging

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

from engine.agent.data_structures import AgentPayload, ToolDescription
from engine.trace.trace_manager import TraceManager
from engine.agent.utils import load_str_to_json

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
    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_instance_name: str,
        payload_schema: str,
    ):
        self.trace_manager = trace_manager
        self.tool_description = tool_description
        self.component_instance_name = component_instance_name
        self.payload_schema = load_str_to_json(payload_schema)

    async def run(self, input_data: dict):
        input_data = input_data[0]  # The input component only take one argument
        filtered_input = {k: input_data[k] for k in self.payload_schema.keys() if k in input_data}
        filtered_input.update({k: self.payload_schema[k] for k in self.payload_schema if k not in input_data})
        with self.trace_manager.start_span(self.component_instance_name) as span:
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.UNKNOWN.value,
                    SpanAttributes.INPUT_VALUE: json.dumps(input_data),
                    SpanAttributes.OUTPUT_VALUE: json.dumps(filtered_input),
                }
            )
            span.set_status(trace_api.StatusCode.OK)
        full_content = ""
        if "full_content" in filtered_input:
            full_content = filtered_input.pop("full_content")
        elif "content" in filtered_input:
            full_content = filtered_input.pop("content")
        elif "messages" in filtered_input:
            full_content = filtered_input.pop("messages")
        else:
            raise ValueError("No content in input")
        return AgentPayload(full_content=full_content, **filtered_input)
