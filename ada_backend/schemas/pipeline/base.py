from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ada_backend.schemas.integration_schema import GraphIntegrationSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionUpdateSchema
from ada_backend.schemas.pipeline.port_instance_schema import InputPortInstanceSchema
from ada_backend.schemas.pipeline.tool_port_configuration_schema import ToolPortConfigurationSchema


class ToolDescriptionReadSchema(BaseModel):
    """Read-only DTO returned by graph-get endpoints. Always computed, never stored."""

    name: str
    description: str
    tool_properties: dict = Field(default_factory=dict)
    required_tool_properties: list[str] = Field(default_factory=list)


class ComponentInstanceSchema(BaseModel):
    """Represents a component instance in the pipeline input"""

    model_config = ConfigDict(extra="ignore")

    id: Optional[UUID] = None  # Optional - if present, update existing instance
    name: Optional[str] = None
    ref: Optional[str] = None
    is_start_node: bool = False
    component_id: UUID
    component_version_id: UUID
    parameters: list[PipelineParameterSchema]
    tool_description_override: Optional[str] = None
    integration: Optional[GraphIntegrationSchema] = None
    field_expressions: list[FieldExpressionUpdateSchema] = Field(
        default_factory=list,
        deprecated=True,
    )
    input_port_instances: list[InputPortInstanceSchema] = Field(default_factory=list)
    port_configurations: Optional[list[ToolPortConfigurationSchema]] = None


class ComponentRelationshipSchema(BaseModel):
    """Represents a relationship between component instances"""

    parent_component_instance_id: UUID
    child_component_instance_id: UUID
    parameter_name: str  # Maps to ComponentParameterDefinition.name
    order: Optional[int] = None
