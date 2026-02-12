from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from ada_backend.schemas.pipeline.base import ComponentInstanceSchema, ComponentRelationshipSchema
from ada_backend.schemas.pipeline.get_pipeline_schema import ComponentInstanceReadSchema
from ada_backend.schemas.pipeline.port_mapping_schema import PortMappingSchema


class PlaygroundFieldType(str, Enum):
    """Types for playground input field rendering."""

    MESSAGES = "messages"
    JSON = "json"
    SIMPLE = "simple"
    FILE = "file"


class EdgeSchema(BaseModel):
    """Represents a graph edge between two nodes by their runnable ids"""

    id: UUID
    origin: UUID
    destination: UUID
    order: Optional[int] = None


class GraphGetResponse(BaseModel):
    """Complete pipeline definition"""

    component_instances: list[ComponentInstanceReadSchema]
    relationships: list[ComponentRelationshipSchema]
    edges: list[EdgeSchema]
    port_mappings: list[PortMappingSchema] = Field(default_factory=list)
    tag_name: Optional[str] = None
    change_log: Optional[str] = None
    last_edited_time: Optional[datetime] = None
    last_edited_user_id: Optional[UUID] = None
    playground_input_schema: Optional[dict] = None
    playground_field_types: Optional[dict[str, PlaygroundFieldType]] = None


class GraphLoadResponse(BaseModel):
    """Response model for loading a graph"""

    component_instances: list[ComponentInstanceReadSchema]
    relationships: list[ComponentRelationshipSchema]
    edges: list[EdgeSchema]


class GraphUpdateSchema(BaseModel):
    """
    Graph structure definition for edges and relationships.
    
    NOTE: component_instances is deprecated. Use the component-level endpoints instead:
    - PUT /projects/{project_id}/graph/{graph_runner_id}/components/{component_instance_id}
    - DELETE /projects/{project_id}/graph/{graph_runner_id}/components/{component_instance_id}
    """

    component_instances: list[ComponentInstanceSchema] = Field(
        default_factory=list,
        deprecated=True,
        description="DEPRECATED: Use component-level endpoints instead. Maintained for backward compatibility.",
    )
    relationships: list[ComponentRelationshipSchema]
    edges: list[EdgeSchema]

    # Multi-port data flow wiring. When omitted, canonical mappings will be auto-created for edges
    port_mappings: list[PortMappingSchema] = Field(default_factory=list)


class GraphUpdateResponse(BaseModel):
    graph_id: UUID
    last_edited_time: Optional[datetime] = None
    last_edited_user_id: Optional[UUID] = None
    playground_input_schema: Optional[dict] = None
    playground_field_types: Optional[dict[str, PlaygroundFieldType]] = None


class ComponentNodeDTO(BaseModel):
    """DTO for component node"""

    id: UUID
    name: str
    is_start_node: bool
    component_instance_id: UUID | None = None
    graph_runner_id: UUID | None = None


class GraphDeployResponse(BaseModel):
    """
    Response returned after deploying a graph, indicating the current
    and previous graph versions bound to the project.
    """

    project_id: UUID
    draft_graph_runner_id: UUID
    prod_graph_runner_id: UUID
    previous_prod_graph_runner_id: Optional[UUID] = None


class GraphSaveVersionResponse(BaseModel):
    """
    Response returned after saving a version from a draft graph runner.
    """

    project_id: UUID
    saved_graph_runner_id: UUID
    tag_version: str
    draft_graph_runner_id: UUID


class ModificationHistoryItem(BaseModel):
    """Represents a single modification history entry"""

    time: datetime
    user_id: Optional[UUID] = None


class GraphModificationHistoryResponse(BaseModel):
    """Response model for graph modification history"""

    history: list[ModificationHistoryItem]
