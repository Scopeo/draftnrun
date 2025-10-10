from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ada_backend.schemas.integration_schema import GraphIntegrationSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema


class ToolDescriptionSchema(BaseModel):
    id: Optional[UUID] = None
    name: str
    description: str
    tool_properties: dict
    required_tool_properties: list[str]


class ComponentInstanceSchema(BaseModel):
    """Represents a component instance in the pipeline input"""

    model_config = ConfigDict(extra="ignore")

    id: Optional[UUID] = None  # Optional - if present, update existing instance
    name: Optional[str] = None
    ref: Optional[str] = None
    is_start_node: bool = False
    component_id: UUID
    parameters: list[PipelineParameterSchema]
    tool_description: Optional[ToolDescriptionSchema] = None
    integration: Optional[GraphIntegrationSchema] = None


class ComponentRelationshipSchema(BaseModel):
    """Represents a relationship between component instances"""

    parent_component_instance_id: UUID
    child_component_instance_id: UUID
    parameter_name: str  # Maps to ComponentParameterDefinition.name
    order: Optional[int] = None
