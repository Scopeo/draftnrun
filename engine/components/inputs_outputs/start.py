import logging
from typing import Any, Dict, Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field, field_validator

from ada_backend.database.models import ParameterType, UIComponent
from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.components.utils import load_str_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

DEFAULT_START_TOOL_DESCRIPTION = ToolDescription(
    name="Start_Tool",
    description="A start node that initializes the workflow with input data.",
    tool_properties={
        "input_data": {
            "type": "json",
            "description": "The starting input data for the workflow",
        },
    },
    required_tool_properties=[],
)


class StartInputs(BaseModel):
    payload_schema: Optional[dict] = Field(
        default=None,
        json_schema_extra={
            "parameter_type": ParameterType.JSON,
            "is_tool_input": False,
            "ui_component": UIComponent.JSON_BUILDER,
            "drives_output_schema": True,
        },
    )
    model_config = {"extra": "allow"}

    @field_validator("payload_schema", mode="before")
    @classmethod
    def parse_payload_schema(cls, v):
        if not v:
            return None
        if isinstance(v, str):
            return load_str_to_json(v)
        return v


class StartOutputs(BaseModel):
    messages: list[dict] = Field(default_factory=list)
    model_config = {"extra": "allow"}


class Start(Component):
    migrated = True
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.UNKNOWN.value

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        **kwargs,
    ):
        super().__init__(trace_manager, tool_description, component_attributes)

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return StartInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return StartOutputs

    @classmethod
    def get_canonical_ports(cls) -> Dict[str, Optional[str]]:
        return {"output": "messages"}

    async def _run_without_io_trace(self, inputs: StartInputs, ctx: Dict[str, Any]) -> StartOutputs:
        payload_schema = inputs.payload_schema or {}
        runtime_data = dict(inputs.model_extra or {})
        for k, v in payload_schema.items():
            if k not in runtime_data:
                runtime_data[k] = v
        messages = runtime_data.pop("messages", [])
        # TODO: remove once all workflows using {{var}} template syntax in downstream system
        # prompts have been migrated to @{{start.var}} field expressions. The graph runner only
        # propagates ctx (not data) to run_context, so extra Start fields must also land in ctx
        # for {{var}} substitution to keep working in unmigrated workflows.
        ctx.update(runtime_data)
        return StartOutputs(messages=messages, **runtime_data)
