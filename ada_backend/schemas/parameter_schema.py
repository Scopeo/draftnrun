from enum import StrEnum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from ada_backend.database.models import ParameterType, UIComponent


class ParameterKind(StrEnum):
    PARAMETER = "parameter"
    INPUT = "input"
    PROMPT = "prompt"


class ParameterBase(BaseModel):
    name: str
    display_order: Optional[int] = None
    kind: ParameterKind = ParameterKind.PARAMETER


class ParameterDefinition(ParameterBase):
    id: UUID
    type: ParameterType
    nullable: bool = False
    default: Optional[str | int | float | bool | dict | list] = None
    ui_component: Optional[UIComponent] = None
    ui_component_properties: Optional[dict] = None
    is_advanced: bool = False
    drives_output_schema: bool = False


class WithValue(BaseModel):
    value: str | int | float | bool | dict | list | None = None


class PromptPinInfo(BaseModel):
    prompt_id: UUID
    prompt_name: str
    pinned_version_id: UUID
    pinned_version_number: int
    latest_version_number: int
    is_latest: bool


class PipelineParameterReadSchema(ParameterDefinition, WithValue):
    """Represents a parameter value in the pipeline input with its definition"""

    is_tool_input: bool = False
    is_prompt_eligible: bool = False
    prompt_pin: Optional[PromptPinInfo] = None


class PipelineParameterSchema(ParameterBase, WithValue):
    """Represents a parameter value in the pipeline input"""


class PipelineParameterV2Schema(ParameterBase, WithValue):
    """Unified parameter for API v2: carries both static values and field expressions.

    kind="parameter" uses ``value`` for the static config value.
    kind="input" uses ``field_expression`` for the wiring data.
    """

    field_expression: Optional[dict] = None
    is_tool_input: bool = False
    description: Optional[str] = None
    port_definition_id: Optional[UUID] = None


class ParameterGroupSchema(BaseModel):
    id: UUID
    name: str
    group_order_within_component_version: int


class ComponentParamDefDTO(ParameterDefinition):
    """Represents a parameter definition for a component"""

    component_version_id: UUID
    is_tool_input: bool = False
    parameter_group_id: Optional[UUID] = None
    parameter_order_within_group: Optional[int] = None
    parameter_group_name: Optional[str] = None
