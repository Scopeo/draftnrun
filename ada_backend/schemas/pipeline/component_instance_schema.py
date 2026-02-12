from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ada_backend.schemas.integration_schema import GraphIntegrationSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionUpdateSchema
from ada_backend.schemas.pipeline.port_mapping_schema import PortMappingSchema


class ToolDescriptionSchema(BaseModel):
    """Tool description for component function calling"""

    id: Optional[UUID] = None
    name: str
    description: str
    tool_properties: dict
    required_tool_properties: list[str]


class ComponentInstanceUpdateSchema(BaseModel):
    """Schema for upserting a single component instance"""

    model_config = ConfigDict(extra="ignore")

    # Component instance fields
    id: UUID  # Required for upsert - create if doesn't exist, update if exists
    name: Optional[str] = None
    ref: Optional[str] = None
    is_start_node: bool = False
    component_id: UUID
    component_version_id: UUID

    # Parameters (can include INPUT kind which will be converted to field expressions)
    parameters: list[PipelineParameterSchema]

    # Optional configurations
    tool_description: Optional[ToolDescriptionSchema] = None
    integration: Optional[GraphIntegrationSchema] = None

    # Field expressions (not deprecated at component level)
    field_expressions: list[FieldExpressionUpdateSchema] = Field(default_factory=list)

    # Port mappings for this component's connections
    port_mappings: list[PortMappingSchema] = Field(default_factory=list)


class ComponentInstanceUpdateResponse(BaseModel):
    """Response after upserting a component instance"""

    component_instance_id: UUID
    graph_runner_id: UUID
    last_edited_time: Optional[datetime] = None
    last_edited_user_id: Optional[UUID] = None


class ComponentInstanceDeleteResponse(BaseModel):
    """Response after deleting a component instance"""

    component_instance_id: UUID
    graph_runner_id: UUID
    deleted_edge_ids: list[UUID]  # Edges that were cascade-deleted
    deleted_at: datetime
