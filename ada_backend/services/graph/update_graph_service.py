import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import EnvType
from ada_backend.repositories.component_repository import (
    get_component_instance_by_id,
    get_component_parameter_definition_by_component_version,
    upsert_sub_component_input,
    get_component_instances_by_ids,
    get_canonical_ports_for_components,
)
from ada_backend.repositories.edge_repository import delete_edge, get_edges, upsert_edge
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.repositories.graph_runner_repository import (
    delete_node,
    get_component_nodes,
    graph_runner_exists,
    insert_graph_runner_and_bind_to_project,
    upsert_component_node,
)
from ada_backend.repositories.port_mapping_repository import (
    delete_port_mappings_for_graph,
    get_output_port_definition_id,
    get_input_port_definition_id,
    get_port_definition_by_id,
)
from ada_backend.database import models as db
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateResponse, GraphUpdateSchema
from ada_backend.services.agent_runner_service import get_agent_for_project
from ada_backend.services.graph.delete_graph_service import delete_component_instances_from_nodes
from ada_backend.services.pipeline.update_pipeline_service import create_or_update_component_instance
from ada_backend.segment_analytics import track_project_saved


LOGGER = logging.getLogger(__name__)


def resolve_component_id_from_instance_id(session: Session, instance_id: UUID) -> UUID:
    """Resolve component ID from a component instance ID"""
    instance = get_component_instance_by_id(session, instance_id)
    if not instance:
        raise ValueError(f"Component instance {instance_id} not found")
    return instance.component_id


def validate_port_definition_types(session: Session, source_port_def_id: UUID, target_port_def_id: UUID) -> None:
    """Validate that source is OUTPUT and target is INPUT"""
    source_port = get_port_definition_by_id(session, source_port_def_id)
    target_port = get_port_definition_by_id(session, target_port_def_id)

    if not source_port:
        raise ValueError(f"Source port definition {source_port_def_id} not found")
    if not target_port:
        raise ValueError(f"Target port definition {target_port_def_id} not found")

    if source_port.port_type != db.PortType.OUTPUT:
        raise ValueError(f"Source port must be OUTPUT type, got {source_port.port_type}")
    if target_port.port_type != db.PortType.INPUT:
        raise ValueError(f"Target port must be INPUT type, got {target_port.port_type}")


def validate_graph_is_draft(session: Session, graph_runner_id: UUID) -> None:
    """
    Validate that the graph runner is in draft mode (env='draft' AND tag_version=null).
    Only draft versions can be modified.

    Raises:
        ValueError: If the graph runner is not in draft mode
    """
    try:
        env_relationship = get_env_relationship_by_graph_runner_id(session, graph_runner_id)
    except ValueError:
        return

    # Get the graph runner to check tag_version
    graph_runner = session.query(db.GraphRunner).filter(db.GraphRunner.id == graph_runner_id).first()
    if not graph_runner:
        raise ValueError(f"Graph runner {graph_runner_id} not found")

    # Check if this is the draft version (env='draft' AND tag_version=null)
    is_draft = env_relationship.environment == EnvType.DRAFT and graph_runner.tag_version is None

    if not is_draft:
        env_name = env_relationship.environment.value if env_relationship.environment else None
        tag = graph_runner.tag_version or None
        raise ValueError(
            f"Cannot modify graph runner {graph_runner_id}: only draft versions"
            "(env='draft' AND tag_version=null) can be modified. "
            f"Current state: env='{env_name}', tag_version='{tag}'. "
            f"Please switch to the draft version to make changes."
        )


# TODO: Refactor to rollback if instantiation failed.
async def update_graph_service(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    graph_project: GraphUpdateSchema,
    env: Optional[EnvType] = None,
    user_id: UUID = None,
    bypass_validation: bool = False,
) -> GraphUpdateResponse:
    """
    Creates or updates a complete graph runner including all component instances,
    their parameters, and relationships.

    Args:
        bypass_validation: If True, skip draft mode validation (use for seeding/migrations only)
    """
    if not graph_runner_exists(session, graph_runner_id):
        LOGGER.info("Creating new graph")
        env = env if env else EnvType.DRAFT
        insert_graph_runner_and_bind_to_project(session, graph_runner_id, project_id=project_id, env=env)
    else:
        # Validate that the graph runner is in draft mode before allowing modifications
        if not bypass_validation:
            validate_graph_is_draft(session, graph_runner_id)
            LOGGER.info(f"Updating existing graph {graph_runner_id} (validated as draft)")
        else:
            LOGGER.warning(f"Updating graph {graph_runner_id} with validation bypassed (seeding/migration mode)")

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
        param_defs = get_component_parameter_definition_by_component_version(session, parent.version_id)
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

    # Port mappings: ensure explicit wiring for all edges (save-time defaults)
    _ensure_port_mappings_for_edges(session, graph_runner_id, graph_project)

    nodes_to_delete = previous_graph_nodes - instance_ids
    if len(nodes_to_delete) > 0:
        delete_component_instances_from_nodes(session, nodes_to_delete)

    # TODO: could use a bulk delete to avoid N+1 here
    for node_id in nodes_to_delete:
        delete_node(session, node_id)
    LOGGER.info("Deleted nodes: {}".format(len(nodes_to_delete)))

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
    explicitly_mapped_pairs: set[tuple[UUID, UUID]] = set()

    if hasattr(graph_project, "port_mappings") and graph_project.port_mappings:
        new_mappings: list[db.PortMapping] = []
        for pm_schema in graph_project.port_mappings:
            # Get component IDs for the instances
            source_component_id = resolve_component_id_from_instance_id(session, pm_schema.source_instance_id)
            target_component_id = resolve_component_id_from_instance_id(session, pm_schema.target_instance_id)

            # Resolve port names to port definition IDs
            source_port_def_id = get_output_port_definition_id(
                session, source_component_id, pm_schema.source_port_name
            )
            if not source_port_def_id:
                raise ValueError(
                    f"Output port '{pm_schema.source_port_name}' not found for component {source_component_id}"
                )

            target_port_def_id = get_input_port_definition_id(session, target_component_id, pm_schema.target_port_name)
            if not target_port_def_id:
                raise ValueError(
                    f"Input port '{pm_schema.target_port_name}' not found for component {target_component_id}"
                )

            validate_port_definition_types(session, source_port_def_id, target_port_def_id)

            new_mappings.append(
                db.PortMapping(
                    graph_runner_id=graph_runner_id,
                    source_instance_id=pm_schema.source_instance_id,
                    source_port_definition_id=source_port_def_id,
                    target_instance_id=pm_schema.target_instance_id,
                    target_port_definition_id=target_port_def_id,
                    dispatch_strategy=pm_schema.dispatch_strategy or "direct",
                )
            )
            explicitly_mapped_pairs.add((pm_schema.source_instance_id, pm_schema.target_instance_id))

        if new_mappings:
            session.bulk_save_objects(new_mappings)
            session.commit()

    # Auto-generate defaults for unmapped edges using canonical ports
    actual_edges: set[tuple[UUID, UUID]] = {(edge.origin, edge.destination) for edge in graph_project.edges}
    unmapped_edges = actual_edges - explicitly_mapped_pairs

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

    auto_generated_mappings: list[db.PortMapping] = []
    for source_instance_id, target_instance_id in unmapped_edges:
        if source_instance_id not in instance_to_component or target_instance_id not in instance_to_component:
            raise ValueError(
                "Unable to infer component ids for one or more unmapped edges; please provide explicit port_mappings."
            )

        source_component_id = instance_to_component[source_instance_id]
        target_component_id = instance_to_component[target_instance_id]

        source_ports = canonical_ports_by_component.get(source_component_id, {})
        target_ports = canonical_ports_by_component.get(target_component_id, {})

        source_port_name = source_ports.get("output") or "output"
        target_port_name = target_ports.get("input") or "input"

        # Resolve port names to port definition IDs
        source_port_def_id = get_output_port_definition_id(session, source_component_id, source_port_name)
        if not source_port_def_id:
            raise ValueError(f"Output port '{source_port_name}' not found for component {source_component_id}")

        target_port_def_id = get_input_port_definition_id(session, target_component_id, target_port_name)
        if not target_port_def_id:
            raise ValueError(f"Input port '{target_port_name}' not found for component {target_component_id}")

        # Validate port definition types
        validate_port_definition_types(session, source_port_def_id, target_port_def_id)

        auto_generated_mappings.append(
            db.PortMapping(
                graph_runner_id=graph_runner_id,
                source_instance_id=source_instance_id,
                source_port_definition_id=source_port_def_id,
                target_instance_id=target_instance_id,
                target_port_definition_id=target_port_def_id,
                dispatch_strategy="direct",
            )
        )

    if auto_generated_mappings:
        session.bulk_save_objects(auto_generated_mappings)
        session.commit()
