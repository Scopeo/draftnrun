from typing import Optional
from uuid import UUID
from pydantic import BaseModel

from ada_backend.database.models import ParameterType, UIComponent


class ParameterBase(BaseModel):
    name: str
    order: Optional[int] = None


class ParameterDefinition(ParameterBase):
    type: ParameterType
    nullable: bool = False
    default: Optional[str] = None
    ui_component: Optional[UIComponent] = None
    ui_component_properties: Optional[dict] = None
    is_advanced: bool = False


class WithValue(BaseModel):
    value: str | int | float | bool | dict | None = None


class PipelineParameterReadSchema(ParameterDefinition, WithValue):
    """Represents a parameter value in the pipeline input with its definition"""


class PipelineParameterSchema(ParameterBase, WithValue):
    """Represents a parameter value in the pipeline input"""


class ComponentParamDefDTO(ParameterDefinition):
    """Represents a parameter definition for a component"""

    component_id: UUID
