import hashlib
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ada_backend.repositories.graph_runner_repository import get_component_nodes, insert_modification_history
from ada_backend.schemas.pipeline.graph_schema import (
    ComponentCreateV2Schema,
    ComponentUpdateV2Schema,
    ComponentV2Response,
    GraphTopologySaveV2Schema,
    GraphUpdateResponse,
)
from ada_backend.services.graph.component_instance_v2_service import (
    create_component_in_graph,
    delete_component_from_graph,
    update_single_component,
)
from ada_backend.services.graph.graph_topology_v2_service import check_optimistic_lock, sync_graph_topology
from ada_backend.services.graph.update_graph_service import validate_graph_is_draft
from ada_backend.utils.redis_client import publish_graph_update_event


def record_modification_history(session: Session, graph_runner_id: UUID, user_id: UUID):
    change_hash = hashlib.sha256(str(uuid4()).encode()).hexdigest()
    return insert_modification_history(session, graph_runner_id, user_id, modification_hash=change_hash)


def create_component_v2(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    user_id: UUID,
    payload: ComponentCreateV2Schema,
) -> ComponentV2Response:
    validate_graph_is_draft(session, graph_runner_id)
    instance_id = create_component_in_graph(session, graph_runner_id, project_id, payload)
    history = record_modification_history(session, graph_runner_id, user_id=user_id)
    publish_graph_update_event(project_id, {
        "type": "graph.changed",
        "graph_runner_id": str(graph_runner_id),
        "action": "component.created",
    })
    return ComponentV2Response(
        instance_id=instance_id,
        label=payload.label,
        is_start_node=payload.is_start_node,
        last_edited_time=history.created_at if history else None,
        last_edited_user_id=history.user_id if history else None,
    )


def update_component_v2(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    instance_id: UUID,
    user_id: UUID,
    payload: ComponentUpdateV2Schema,
) -> ComponentV2Response:
    validate_graph_is_draft(session, graph_runner_id)
    update_single_component(session, graph_runner_id, project_id, instance_id, payload)
    history = record_modification_history(session, graph_runner_id, user_id=user_id)
    publish_graph_update_event(project_id, {
        "type": "graph.changed",
        "graph_runner_id": str(graph_runner_id),
        "action": "component.updated",
    })

    nodes = get_component_nodes(session, graph_runner_id)
    node = next((n for n in nodes if n.id == instance_id), None)
    return ComponentV2Response(
        instance_id=instance_id,
        label=node.name if node else payload.label,
        is_start_node=node.is_start_node if node else (payload.is_start_node or False),
        last_edited_time=history.created_at if history else None,
        last_edited_user_id=history.user_id if history else None,
    )


def delete_component_v2(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    instance_id: UUID,
    user_id: UUID,
) -> None:
    validate_graph_is_draft(session, graph_runner_id)
    delete_component_from_graph(session, graph_runner_id, instance_id)
    record_modification_history(session, graph_runner_id, user_id=user_id)
    publish_graph_update_event(project_id, {
        "type": "graph.changed",
        "graph_runner_id": str(graph_runner_id),
        "action": "component.deleted",
    })


def save_graph_topology_v2(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    user_id: UUID,
    payload: GraphTopologySaveV2Schema,
) -> GraphUpdateResponse:
    validate_graph_is_draft(session, graph_runner_id)
    check_optimistic_lock(session, graph_runner_id, payload.last_edited_time)
    sync_graph_topology(
        session,
        graph_runner_id=graph_runner_id,
        nodes=payload.nodes,
        edges=payload.edges,
        relationships=payload.relationships,
    )
    history = record_modification_history(session, graph_runner_id, user_id=user_id)
    publish_graph_update_event(project_id, {
        "type": "graph.changed",
        "graph_runner_id": str(graph_runner_id),
        "action": "topology.updated",
    })
    return GraphUpdateResponse(
        graph_id=graph_runner_id,
        last_edited_time=history.created_at if history else None,
        last_edited_user_id=history.user_id if history else None,
    )
