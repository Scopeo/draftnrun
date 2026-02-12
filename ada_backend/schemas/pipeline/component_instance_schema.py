from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ada_backend.schemas.integration_schema import GraphIntegrationSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema


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
    id: Optional[UUID] = None
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


class DependentExpressionSchema(BaseModel):
    """A field expression that references a component instance being deleted."""

    target_instance_id: UUID
    field_name: str


class ComponentInstanceDeleteBlockedResponse(BaseModel):
    """Response when delete is blocked due to dependent field expressions (409)."""

    detail: str
    component_instance_id: UUID
    dependents: list[DependentExpressionSchema]
