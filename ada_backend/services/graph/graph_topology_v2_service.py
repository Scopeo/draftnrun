import logging
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ada_backend.repositories.component_repository import (
    get_component_instance_by_id,
    get_component_parameter_definition_by_component_version,
    upsert_sub_component_input,
)
from ada_backend.repositories.edge_repository import delete_edge, get_edges, upsert_edge
from ada_backend.repositories.graph_runner_repository import (
    get_component_nodes,
    get_latest_modification_history,
    graph_runner_exists,
    upsert_component_node,
)
from ada_backend.schemas.pipeline.graph_schema import (
    GraphMapEdgeSchema,
    GraphMapNodeRefSchema,
    GraphMapRelationshipSchema,
    GraphTopologyNodeSchema,
)
from ada_backend.services.errors import GraphConflictError

LOGGER = logging.getLogger(__name__)


def check_optimistic_lock(session: Session, graph_runner_id: UUID, last_edited_time: datetime | None):
    if not last_edited_time:
        return
    latest_history = get_latest_modification_history(session, graph_runner_id)
    if latest_history and latest_history.created_at and latest_history.created_at > last_edited_time:
        raise GraphConflictError(graph_runner_id)


def sync_graph_topology(
    session: Session,
    graph_runner_id: UUID,
    nodes: list[GraphTopologyNodeSchema],
    edges: list[GraphMapEdgeSchema],
    relationships: list[GraphMapRelationshipSchema],
) -> None:
    existing_node_ids = {node.id for node in get_component_nodes(session, graph_runner_id)}
    payload_node_ids = {node.instance_id for node in nodes}
    missing = payload_node_ids - existing_node_ids
    if missing:
        raise ValueError(f"Nodes referenced in topology do not exist in graph: {missing}")

    for node in nodes:
        upsert_component_node(
            session,
            graph_runner_id=graph_runner_id,
            component_instance_id=node.instance_id,
            is_start_node=node.is_start_node,
        )

    previous_edge_ids = {edge.id for edge in get_edges(session, graph_runner_id)}
    new_edge_ids: set[UUID] = set()
    for edge in edges:
        origin = _resolve_edge_ref(edge.from_node, payload_node_ids)
        destination = _resolve_edge_ref(edge.to_node, payload_node_ids)

        if graph_runner_exists(session, destination) or graph_runner_exists(session, origin):
            raise ValueError("Nested graphs are not supported")

        edge_id = edge.id or uuid4()
        new_edge_ids.add(edge_id)
        upsert_edge(
            session,
            id=edge_id,
            source_node_id=origin,
            target_node_id=destination,
            graph_runner_id=graph_runner_id,
            order=edge.order,
        )

    for edge_id in previous_edge_ids - new_edge_ids:
        delete_edge(session, edge_id)

    _sync_relationships(session, payload_node_ids, relationships)


def _resolve_edge_ref(ref: GraphMapNodeRefSchema, valid_ids: set[UUID]) -> UUID:
    if ref.id:
        if ref.id not in valid_ids:
            raise ValueError(f"Edge references unknown node id '{ref.id}'")
        return ref.id
    raise ValueError("Edge node references must use 'id' in topology save")


def _sync_relationships(
    session: Session,
    valid_ids: set[UUID],
    relationships: list[GraphMapRelationshipSchema],
) -> None:
    for relation in relationships:
        parent_id = _resolve_edge_ref(relation.parent, valid_ids)
        child_id = _resolve_edge_ref(relation.child, valid_ids)

        parent = get_component_instance_by_id(session, parent_id)
        if not parent:
            raise ValueError(f"Relationship parent component instance {parent_id} not found")

        param_defs = (
            get_component_parameter_definition_by_component_version(session, parent.component_version_id) or []
        )
        param_def = next((p for p in param_defs if p.name == relation.parameter_name), None)
        if not param_def:
            raise ValueError(
                f"Parameter '{relation.parameter_name}' not found in "
                f"component definitions for component version '{parent.component_version_id}'"
            )

        upsert_sub_component_input(
            session=session,
            parent_component_instance_id=parent_id,
            child_component_instance_id=child_id,
            parameter_definition_id=param_def.id,
            order=relation.order,
        )
