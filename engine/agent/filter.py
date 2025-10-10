import logging
from typing import Type, Any, Optional

from openinference.semconv.trace import OpenInferenceSpanKindValues
from jsonschema_pydantic import jsonschema_to_pydantic
from pydantic import BaseModel, Field

from engine.agent.agent import Agent
from engine.agent.types import (
    ToolDescription,
    ChatMessage,
    ComponentAttributes,
)
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


class FilterInputs(BaseModel):
    messages: Optional[list[ChatMessage]] = Field(default=None, description="The messages to filter.")
    error: Optional[str] = Field(default=None, description="Error message if any.")
    artifacts: dict[str, Any] = Field(default_factory=dict, description="Artifacts to filter.")
    is_final: bool = Field(default=False, description="Whether this is a final output.")
    # Allow any other fields to be passed through
    model_config = {"extra": "allow"}


class FilterOutputs(BaseModel):
    output: str = Field(description="The string content of the final message from the agent.")
    full_message: ChatMessage = Field(description="The full final message object from the agent.")
    is_final: bool = Field(default=False, description="Indicates if this is the final output of the agent.")
    artifacts: dict[str, Any] = Field(default_factory=dict, description="Artifacts produced by the agent.")


class Filter(Agent):
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
        # The filter expects messages as input and produces output string
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
        self.filtering_json_schema = load_str_to_json(filtering_json_schema)
        self.output_model = jsonschema_to_pydantic(self.filtering_json_schema)

    async def _run_without_io_trace(self, inputs: FilterInputs, ctx: dict) -> FilterOutputs:
        # Convert inputs to dict for filtering
        input_data = inputs.model_dump(exclude_none=True)

        # Apply the JSON schema filter
        filtered_output = self.output_model(**input_data)
        filtered_dict = filtered_output.model_dump(exclude_unset=True, exclude_none=True)

        # Extract filtered fields
        messages = filtered_dict.get("messages", [])
        error = filtered_dict.get("error")
        artifacts = filtered_dict.get("artifacts", {})
        is_final = filtered_dict.get("is_final", False)

        # Convert message dicts to ChatMessage objects if needed
        if messages and isinstance(messages[0], dict):
            messages = [ChatMessage(**msg) for msg in messages]

        # Get the last message as the full_message output
        full_message = messages[-1] if messages else ChatMessage(role="assistant", content="")

        # Extract string content from the last message
        output = full_message.content or ""

        return FilterOutputs(
            output=output,
            full_message=full_message,
            is_final=is_final,
            artifacts=artifacts,
        )
