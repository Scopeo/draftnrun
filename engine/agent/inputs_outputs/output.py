import json
import logging

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from jsonschema_pydantic import jsonschema_to_pydantic

from engine.agent.agent import ToolDescription
from engine.trace.trace_manager import TraceManager
from engine.agent.utils import load_str_to_json

LOGGER = logging.getLogger(__name__)

DEFAULT_OUTPUT_TOOL_DESCRIPTION = ToolDescription(
    name="Output_Tool",
    description=("An output tool that filters the input data to return an AgentPayload."),
    tool_properties={
        "input_data": {
            "type": "json",
            "description": "An output tool",
        },
    },
    required_tool_properties=[],
)


class Output:
    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_instance_name: str,
        output_schema: str,
    ):
        self.trace_manager = trace_manager
        self.tool_description = tool_description
        self.component_instance_name = component_instance_name
        self.output_schema = load_str_to_json(output_schema)
        self.output_model = jsonschema_to_pydantic(self.output_schema)

    async def run(self, output_data: dict):
        filtered_output = self.output_model(**output_data)
        filtered_output = filtered_output.model_dump(exclude_unset=True, exclude_none=True)
        with self.trace_manager.start_span(self.component_instance_name) as span:
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                    SpanAttributes.INPUT_VALUE: json.dumps(output_data),
                    SpanAttributes.OUTPUT_VALUE: json.dumps(filtered_output),
                }
            )
            span.set_status(trace_api.StatusCode.OK)
        return filtered_output
