import logging
from typing import Any, Optional, Type

from jsonschema_pydantic import jsonschema_to_pydantic
from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field

from engine.components.component import Component
from engine.components.types import (
    ChatMessage,
    ComponentAttributes,
    ToolDescription,
)
from engine.components.utils import load_str_to_json
from engine.trace.trace_manager import TraceManager

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


class FilterInputs(BaseModel):
    messages: Optional[list[ChatMessage]] = Field(default=None, description="The messages to filter.")
    error: Optional[str] = Field(default=None, description="Error message if any.")
    artifacts: dict[str, Any] = Field(default_factory=dict, description="Artifacts to filter.")
    is_final: bool = Field(default=False, description="Whether this is a final output.")
    filtering_json_schema: Optional[str] = Field(
        default=None,
        description="JSON schema for filtering data.",
        json_schema_extra={"disabled_as_input": True, "is_tool_input": False},
    )
    # Allow any other fields to be passed through
    model_config = {"extra": "allow"}


class FilterOutputs(BaseModel):
    output: str = Field(description="The string content of the final message from the agent.")
    is_final: bool = Field(default=False, description="Indicates if this is the final output of the agent.")
    artifacts: dict[str, Any] = Field(default_factory=dict, description="Artifacts produced by the agent.")


class Filter(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.UNKNOWN.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return FilterInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return FilterOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "messages", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        filtering_json_schema: str,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.filtering_json_schema = filtering_json_schema

    async def _run_without_io_trace(self, inputs: FilterInputs, ctx: dict) -> FilterOutputs:
        filtering_json_schema = inputs.filtering_json_schema or self.filtering_json_schema
        try:
            filtering_json_schema_dict = load_str_to_json(filtering_json_schema)
        except ValueError as e:
            raise ValueError(f"Invalid 'filtering_json_schema' parameter: {e}") from e
        output_model = jsonschema_to_pydantic(filtering_json_schema_dict)

        # Convert inputs to dict for filtering
        input_data = inputs.model_dump(exclude_none=True)

        # Apply the JSON schema filter
        filtered_output = output_model(**input_data)
        filtered_dict = filtered_output.model_dump(exclude_unset=True, exclude_none=True)

        # Extract filtered fields
        messages = filtered_dict.get("messages", [])
        artifacts = filtered_dict.get("artifacts", {})
        is_final = filtered_dict.get("is_final", False)

        # Convert message dicts to ChatMessage objects if needed
        if messages and isinstance(messages[0], dict):
            messages = [ChatMessage(**msg) for msg in messages]

        output = messages[-1].to_string() if messages else ""

        return FilterOutputs(
            output=output,
            is_final=is_final,
            artifacts=artifacts,
        )
