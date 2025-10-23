import logging
from typing import Type

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from pydantic import BaseModel

from engine.agent.types import ToolDescription, ComponentAttributes, AgentPayload, NodeData
from engine.trace.trace_manager import TraceManager
from engine.agent.json_schema_utils import parse_json_schema_string
from engine.trace.serializer import serialize_to_json

LOGGER = logging.getLogger(__name__)

DEFAULT_START_TOOL_DESCRIPTION = ToolDescription(
    name="Start_Tool",
    description=("A start node that initializes the workflow with input data."),
    tool_properties={
        "input_data": {
            "type": "json",
            "description": "The starting input data for the workflow",
        },
    },
    required_tool_properties=[],
)


class Start:
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
        # Parse the JSON Schema string or dict
        if isinstance(payload_schema, str):
            self.payload_schema = parse_json_schema_string(payload_schema)
        else:
            # If it's already a dict, use it directly
            self.payload_schema = payload_schema

    def get_canonical_ports(self) -> dict[str, str | None]:
        return {"output": "messages"}

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        from engine.legacy_compatibility import create_legacy_input_schema

        return create_legacy_input_schema()

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        from engine.legacy_compatibility import create_legacy_input_output_schema

        return create_legacy_input_output_schema()

    async def run(self, input_data: AgentPayload | dict | NodeData) -> NodeData:
        if isinstance(input_data, NodeData):
            base: dict = dict(input_data.data or {})
            incoming_ctx = input_data.ctx.copy()
        elif isinstance(input_data, AgentPayload):
            base = input_data.model_dump()
            incoming_ctx = {}
        else:
            base = dict(input_data)
            incoming_ctx = {}

        filtered_input = base.copy()

        if isinstance(self.payload_schema, dict) and "properties" in self.payload_schema:
            for key, prop_schema in self.payload_schema["properties"].items():
                if key not in filtered_input and "default" in prop_schema:
                    filtered_input[key] = prop_schema["default"]

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

        template_vars = {}
        file_content = {}
        file_urls = {}

        for k, v in filtered_input.items():
            if k == "messages":
                continue
            elif k == "template_vars" and isinstance(v, dict):
                template_vars.update({tk: str(tv) for tk, tv in v.items()})
            elif k == "file_urls" and isinstance(v, dict):
                file_urls.update(v)
            elif k.endswith("_file_content") or k.endswith("_file_data"):
                file_content[k] = v
            elif k.endswith("_file_url") or k.endswith("_url"):
                file_urls[k] = v
            else:
                template_vars[k] = str(v)

        ctx = incoming_ctx
        ctx["template_vars"] = template_vars
        if file_content:
            ctx["file_content"] = file_content
        if file_urls:
            ctx["file_urls"] = file_urls

        messages = filtered_input.get("messages", [])
        return NodeData(data={"messages": messages}, ctx=ctx)
