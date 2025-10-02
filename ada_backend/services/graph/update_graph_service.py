import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import EnvType
from ada_backend.repositories.component_repository import (
    get_component_instance_by_id,
    get_component_parameter_definition_by_component_id,
    upsert_sub_component_input,
    get_component_instances_by_ids,
)
from ada_backend.repositories.edge_repository import delete_edge, get_edges, upsert_edge
from ada_backend.repositories.graph_runner_repository import (
    delete_node,
    get_component_nodes,
    graph_runner_exists,
    insert_graph_runner_and_bind_to_project,
    upsert_component_node,
    delete_port_mappings_for_graph,
)
from ada_backend.database import models as db
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateResponse, GraphUpdateSchema
from ada_backend.repositories.component_repository import get_canonical_ports_for_components
from ada_backend.services.agent_runner_service import get_agent_for_project
from ada_backend.services.graph.delete_graph_service import delete_component_instances_from_nodes
from ada_backend.services.pipeline.update_pipeline_service import create_or_update_component_instance
from ada_backend.segment_analytics import track_project_saved


LOGGER = logging.getLogger(__name__)


# TODO: Refactor to rollback if instantiation failed.
async def update_graph_service(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    graph_project: GraphUpdateSchema,
    env: Optional[EnvType] = None,
    user_id: UUID = None,
) -> GraphUpdateResponse:
    """
    Creates or updates a complete graph runner including all component instances,
    their parameters, and relationships.
    """
    if not graph_runner_exists(session, graph_runner_id):
        LOGGER.info("Creating new graph")
        env = env if env else EnvType.DRAFT
        insert_graph_runner_and_bind_to_project(session, graph_runner_id, project_id=project_id, env=env)
    # TODO: Add the get_graph_runner_nodes function when we will handle nested graphs
    previous_graph_nodes = set(node.id for node in get_component_nodes(session, graph_runner_id))
    previous_edge_ids = set(edge.id for edge in get_edges(session, graph_runner_id))

    # Create/update all component instances
    instance_ids = set()
    for instance in graph_project.component_instances:
        instance_id = create_or_update_component_instance(session, instance, project_id)
        upsert_component_node(
            session,
            graph_runner_id=graph_runner_id,
            component_instance_id=instance.id,
            is_start_node=instance.is_start_node,
        )
        instance_ids.add(instance_id)

    # Create relationships
    for relation in graph_project.relationships:
        # Validate that both components exist
        if not (
            relation.parent_component_instance_id in instance_ids
            and relation.child_component_instance_id in instance_ids
        ):
            raise ValueError("Invalid relationship: component instance not found")

        # Get parameter definition ID from name
        parent = get_component_instance_by_id(session, relation.parent_component_instance_id)
        if not parent:
            raise ValueError("Invalid relationship: parent component instance not found")
        # TODO: Refactor to repository function that takes name and component_id or with dictionary for faster lookup
        param_defs = get_component_parameter_definition_by_component_id(session, parent.component_id)
        param_def = next((p for p in param_defs if p.name == relation.parameter_name), None)
        if not param_def:
            raise ValueError(
                f"Parameter '{relation.parameter_name}' not found in "
                f"component definitions for component '{parent.component.name}'"
            )

        # Create relationship
        upsert_sub_component_input(
            session=session,
            parent_component_instance_id=relation.parent_component_instance_id,
            child_component_instance_id=relation.child_component_instance_id,
            parameter_definition_id=param_def.id,
            order=relation.order,
        )

    for edge in graph_project.edges:
        if graph_runner_exists(session, edge.destination) or graph_runner_exists(session, edge.origin):
            raise ValueError("Nested graphs are not supported")

        upsert_edge(
            session,
            id=edge.id,
            source_node_id=edge.origin,
            target_node_id=edge.destination,
            graph_runner_id=graph_runner_id,
            order=edge.order,
        )

    edge_ids_to_delete = previous_edge_ids - {edge.id for edge in graph_project.edges}
    LOGGER.info("Deleting edges: {}".format(len(edge_ids_to_delete)))
    # TODO: could use a bulk delete to avoid N+1 here
    for edge_id in edge_ids_to_delete:
        delete_edge(session, edge_id)

    nodes_to_delete = previous_graph_nodes - instance_ids
    if len(nodes_to_delete) > 0:
        delete_component_instances_from_nodes(session, nodes_to_delete)

    # TODO: could use a bulk delete to avoid N+1 here
    for node_id in nodes_to_delete:
        delete_node(session, node_id)
    LOGGER.info("Deleted nodes: {}".format(len(nodes_to_delete)))

    # --- Port mappings: ensure explicit wiring for all edges (save-time defaults) ---
    _ensure_port_mappings_for_edges(session, graph_runner_id, graph_project)

    await get_agent_for_project(
        session,
        project_id=project_id,
        graph_runner_id=graph_runner_id,
    )
    if user_id:
        track_project_saved(user_id, project_id)
    return GraphUpdateResponse(graph_id=graph_runner_id)


def _ensure_port_mappings_for_edges(
    session: Session,
    graph_runner_id: UUID,
    graph_project: GraphUpdateSchema,
) -> None:
    # Full replacement (PUT) semantics for port mappings
    delete_port_mappings_for_graph(session, graph_runner_id)
    provided_pairs: set[tuple[UUID, UUID]] = set()

    if hasattr(graph_project, "port_mappings") and graph_project.port_mappings:
        new_mappings: list[db.PortMapping] = []
        for pm_schema in graph_project.port_mappings:
            new_mappings.append(
                db.PortMapping(
                    graph_runner_id=graph_runner_id,
                    source_instance_id=pm_schema.source_instance_id,
                    source_port_name=pm_schema.source_port_name,
                    target_instance_id=pm_schema.target_instance_id,
                    target_port_name=pm_schema.target_port_name,
                    dispatch_strategy=pm_schema.dispatch_strategy or "direct",
                )
            )
            provided_pairs.add((pm_schema.source_instance_id, pm_schema.target_instance_id))

        if new_mappings:
            session.bulk_save_objects(new_mappings)
            session.commit()

    # Auto-generate defaults for unmapped edges using canonical ports
    actual_edges: set[tuple[UUID, UUID]] = {(edge.origin, edge.destination) for edge in graph_project.edges}
    unmapped_edges = actual_edges - provided_pairs

    if not unmapped_edges:
        return

    instance_to_component: dict[UUID, UUID] = {}
    for inst in graph_project.component_instances:
        if inst.id and inst.component_id:
            instance_to_component[inst.id] = inst.component_id

    missing_instance_ids = {iid for pair in unmapped_edges for iid in pair if iid not in instance_to_component}
    if missing_instance_ids:
        db_instances = get_component_instances_by_ids(session, list(missing_instance_ids))
        for iid, db_inst in db_instances.items():
            instance_to_component[iid] = db_inst.component_id

    component_ids = list(
        {instance_to_component[s] for s, t in unmapped_edges} | {instance_to_component[t] for s, t in unmapped_edges}
    )
    canonical_ports_by_component = get_canonical_ports_for_components(session, component_ids)

    auto_mappings: list[db.PortMapping] = []
    for source_iid, target_iid in unmapped_edges:
        if source_iid not in instance_to_component or target_iid not in instance_to_component:
            raise ValueError(
                "Unable to infer component ids for one or more unmapped edges; please provide explicit port_mappings."
            )

        source_cid = instance_to_component[source_iid]
        target_cid = instance_to_component[target_iid]

        source_ports = canonical_ports_by_component.get(source_cid, {})
        target_ports = canonical_ports_by_component.get(target_cid, {})

        source_port_name = source_ports.get("output") or "output"
        target_port_name = target_ports.get("input") or "input"

        auto_mappings.append(
            db.PortMapping(
                graph_runner_id=graph_runner_id,
                source_instance_id=source_iid,
                source_port_name=source_port_name,
                target_instance_id=target_iid,
                target_port_name=target_port_name,
                dispatch_strategy="direct",
            )
        )

    if auto_mappings:
        session.bulk_save_objects(auto_mappings)
        session.commit()
