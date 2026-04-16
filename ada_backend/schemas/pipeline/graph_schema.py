from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from ada_backend.schemas.pipeline.base import ComponentInstanceSchema, ComponentRelationshipSchema
from ada_backend.schemas.pipeline.get_pipeline_schema import ComponentInstanceReadSchema


class PlaygroundFieldType(str, Enum):
    """Types for playground input field rendering."""

    MESSAGES = "messages"
    JSON = "json"
    SIMPLE = "simple"
    FILE = "file"


def _coerce_edge_endpoint(v):
    """Accept both a plain UUID and a dict like {"instance_id": "uuid", ...}."""
    if isinstance(v, dict):
        for key in ("instance_id", "id"):
            if key in v:
                return UUID(str(v[key])) if not isinstance(v[key], UUID) else v[key]
        raise ValueError(f"Edge endpoint dict must contain 'instance_id' or 'id', got keys: {list(v.keys())}")
    return v


class EdgeSchema(BaseModel):
    """Represents a graph edge between two nodes by their runnable ids"""

    id: UUID
    origin: UUID
    destination: UUID
    order: Optional[int] = None

    @field_validator("origin", "destination", mode="before")
    @classmethod
    def coerce_endpoint(cls, v):
        return _coerce_edge_endpoint(v)


class GraphGetResponse(BaseModel):
    """Complete pipeline definition"""

    component_instances: list[ComponentInstanceReadSchema]
    relationships: list[ComponentRelationshipSchema]
    edges: list[EdgeSchema]
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
    """Complete pipeline definition"""

    component_instances: list[ComponentInstanceSchema]
    relationships: list[ComponentRelationshipSchema]
    edges: list[EdgeSchema]

    # Optional optimistic locking: pass the last_edited_time from a previous update_graph
    # response. The backend returns 409 Conflict if the graph was modified since that timestamp.
    last_edited_time: Optional[datetime] = None


class GraphMapNodeRefSchema(BaseModel):
    id: Optional[UUID] = None
    file_key: Optional[str] = None


class GraphInstanceSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_key: Optional[str] = None
    instance_id: Optional[UUID] = Field(default=None, validation_alias=AliasChoices("instance_id", "id"))
    label: Optional[str] = Field(default=None, validation_alias=AliasChoices("label", "name"))
    is_start_node: bool = False


class GraphMapEdgeSchema(BaseModel):
    id: Optional[UUID] = None
    from_node: GraphMapNodeRefSchema = Field(alias="from")
    to_node: GraphMapNodeRefSchema = Field(alias="to")
    order: Optional[int] = None


class GraphMapRelationshipSchema(BaseModel):
    parent: GraphMapNodeRefSchema
    child: GraphMapNodeRefSchema
    parameter_name: str
    order: Optional[int] = None


class GraphMapSchema(BaseModel):
    nodes: list[GraphInstanceSchema]
    edges: list[GraphMapEdgeSchema] = Field(default_factory=list)
    relationships: list[GraphMapRelationshipSchema] = Field(default_factory=list)


class GraphComponentFileSchema(BaseModel):
    file_key: str
    id: Optional[UUID] = None
    component_id: UUID
    component_version_id: UUID
    parameters: list[dict] = Field(default_factory=list)
    input_port_instances: list[dict] = Field(default_factory=list)
    port_configurations: Optional[list[dict]] = None
    integration: Optional[dict] = None
    tool_description_override: Optional[str] = None


class GraphSaveV2Schema(BaseModel):
    graph_map: GraphMapSchema
    components: list[GraphComponentFileSchema]
    last_edited_time: Optional[datetime] = None


class ComponentCreateV2Schema(BaseModel):
    component_id: UUID
    component_version_id: UUID
    label: str
    is_start_node: bool = False
    parameters: list[dict] = Field(default_factory=list)
    input_port_instances: list[dict] = Field(default_factory=list)
    port_configurations: Optional[list[dict]] = None
    integration: Optional[dict] = None
    tool_description_override: Optional[str] = None


class ComponentUpdateV2Schema(BaseModel):
    parameters: list[dict] = Field(default_factory=list)
    input_port_instances: list[dict] = Field(default_factory=list)
    port_configurations: Optional[list[dict]] = None
    integration: Optional[dict] = None
    tool_description_override: Optional[str] = None
    label: Optional[str] = None
    is_start_node: Optional[bool] = None


class ComponentV2Response(BaseModel):
    instance_id: UUID
    label: Optional[str] = None
    is_start_node: bool = False
    last_edited_time: Optional[datetime] = None
    last_edited_user_id: Optional[UUID] = None


class GraphTopologyNodeSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    instance_id: UUID = Field(validation_alias=AliasChoices("instance_id", "id"))
    label: Optional[str] = Field(default=None, validation_alias=AliasChoices("label", "name"))
    is_start_node: bool = False


class GraphTopologySaveV2Schema(BaseModel):
    nodes: list[GraphTopologyNodeSchema]
    edges: list[GraphMapEdgeSchema] = Field(default_factory=list)
    relationships: list[GraphMapRelationshipSchema] = Field(default_factory=list)
    last_edited_time: Optional[datetime] = None


class GraphGetV2Response(BaseModel):
    graph_map: GraphMapSchema
    tag_name: Optional[str] = None
    change_log: Optional[str] = None
    last_edited_time: Optional[datetime] = None
    last_edited_user_id: Optional[UUID] = None


class AutoGeneratedFieldExpression(BaseModel):
    component_instance_id: UUID
    field_name: str
    expression_json: dict
    expression_text: Optional[str] = None


class GraphUpdateResponse(BaseModel):
    graph_id: UUID
    last_edited_time: Optional[datetime] = None
    last_edited_user_id: Optional[UUID] = None
    playground_input_schema: Optional[dict] = None
    playground_field_types: Optional[dict[str, PlaygroundFieldType]] = None
    auto_generated_field_expressions: list[AutoGeneratedFieldExpression] = Field(default_factory=list)


class ComponentNodeDTO(BaseModel):
    """DTO for component node"""

    id: UUID
    name: str
    is_start_node: bool
    is_trigger: bool = False
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
