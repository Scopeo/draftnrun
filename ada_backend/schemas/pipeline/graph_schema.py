from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from ada_backend.schemas.pipeline.base import ComponentRelationshipSchema, ComponentInstanceSchema
from ada_backend.schemas.pipeline.get_pipeline_schema import ComponentInstanceReadSchema
from ada_backend.schemas.pipeline.port_mapping_schema import PortMappingSchema


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


class GraphLoadResponse(BaseModel):
    """Response model for loading a graph"""

    component_instances: list[ComponentInstanceReadSchema]
    relationships: list[ComponentRelationshipSchema]
    edges: list[EdgeSchema]


class GraphUpdateSchema(BaseModel):
    """Complete pipeline definition"""

    component_instances: list[ComponentInstanceSchema]
    relationships: list[ComponentRelationshipSchema]
    edges: list[EdgeSchema]

    # Multi-port data flow wiring. When omitted, canonical mappings will be auto-created for edges
    port_mappings: list[PortMappingSchema] = Field(default_factory=list)


class GraphUpdateResponse(BaseModel):
    graph_id: UUID


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
