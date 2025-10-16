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
        return {"output": "messages", "rag_filter": "rag_filter"}

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
    async def run(self, input_data: AgentPayload | dict | NodeData) -> NodeData:
        # Normalize input to a plain dict
        # TODO: Remove after I/O refactor migration
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

        # "messages" go in data, all other fields go in ctx
        ctx = incoming_ctx
        for k, v in filtered_input.items():
            if k == "messages":
                continue
            ctx[k] = v

        # Extract template vars (everything except messages and file-related fields)
        template_vars = {}
        file_content = {}
        file_urls = {}
        rag_filter = {}

        for k, v in filtered_input.items():
            if k == "messages":
                continue
            elif k == "template_vars" and isinstance(v, dict):
                # {"template_vars": {"username": "John"}}
                template_vars.update({tk: str(tv) for tk, tv in v.items()})
            elif k == "file_urls" and isinstance(v, dict):
                # {"file_urls": {"cs_book": "url"}}
                file_urls.update(v)
            elif k.endswith("_file_content") or k.endswith("_file_data"):
                # LEGACY: Individual file content fields (deprecated)
                file_content[k] = v
            elif k.endswith("_file_url") or k.endswith("_url"):
                # LEGACY: Individual file URL fields (deprecated)
                file_urls[k] = v
            elif k == "rag_filter":
                rag_filter = v
            else:
                # LEGACY: Flat template variables (deprecated)
                # {"username": "John", "company": "Acme"}
                # TODO: Remove this support once all frontends use nested structure
                template_vars[k] = str(v)

        # Return NodeData with messages in data and all other fields in ctx
        messages = filtered_input.get("messages", [])
        return NodeData(data={"messages": messages, "rag_filter": rag_filter}, ctx=ctx)
