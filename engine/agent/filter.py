import json
import logging

from opentelemetry import trace as trace_api
from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues
from jsonschema_pydantic import jsonschema_to_pydantic

from engine.agent.agent import ComponentAttributes, ToolDescription, AgentPayload, ChatMessage
from engine.trace.trace_manager import TraceManager
from engine.agent.utils import load_str_to_json

LOGGER = logging.getLogger(__name__)

DEFAULT_FILTER_TOOL_DESCRIPTION = ToolDescription(
    name="Filter_Tool",
    description=("An filter tool that filters the input data to return an AgentPayload."),
    tool_properties={
        "input_data": {
            "type": "json",
            "description": "An filter tool",
        },
    },
    required_tool_properties=[],
)


class Filter:
    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        filtering_json_schema: str,
    ):
        self.trace_manager = trace_manager
        self.tool_description = tool_description
        self.component_attributes = component_attributes
        self.filtering_json_schema = load_str_to_json(filtering_json_schema)
        self.output_model = jsonschema_to_pydantic(self.filtering_json_schema)

    async def run(self, output_data: AgentPayload | dict):

        if isinstance(output_data, AgentPayload):
            output_data = output_data.model_dump()
        filtered_output = self.output_model(**output_data)
        filtered_dict = filtered_output.model_dump(exclude_unset=True, exclude_none=True)

        messages = filtered_dict.get("messages", [])
        error = filtered_dict.get("error")
        artifacts = filtered_dict.get("artifacts", {})
        is_final = filtered_dict.get("is_final", False)

        if messages and isinstance(messages[0], dict):
            messages = [ChatMessage(**msg) for msg in messages]

        result = AgentPayload(messages=messages, error=error, artifacts=artifacts, is_final=is_final)

        with self.trace_manager.start_span(self.component_attributes.component_instance_name) as span:
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.UNKNOWN.value,
                    SpanAttributes.INPUT_VALUE: json.dumps(output_data),
                    SpanAttributes.OUTPUT_VALUE: json.dumps(filtered_dict),
                }
            )
            span.set_status(trace_api.StatusCode.OK)
        return result
