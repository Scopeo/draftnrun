import hashlib
import json
import logging
from collections import defaultdict
from typing import Iterator, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import EnvType
from ada_backend.repositories.component_repository import (
    get_canonical_ports_for_component_versions,
    get_component_instance_by_id,
    get_component_instances_by_ids,
    get_component_parameter_definition_by_component_version,
    get_output_ports_for_component_version,
    upsert_sub_component_input,
)
from ada_backend.repositories.edge_repository import delete_edge, get_edges, get_edges_for_instance_node, upsert_edge
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.repositories.field_expression_repository import (
    create_field_expression,
    update_field_expression,
)
from ada_backend.repositories.graph_runner_repository import (
    delete_node,
    get_component_nodes,
    get_latest_modification_history,
    graph_runner_exists,
    insert_graph_runner_and_bind_to_project,
    insert_modification_history,
    is_start_node,
    upsert_component_node,
)
from ada_backend.repositories.input_port_instance_repository import (
    create_input_port_instance,
    delete_input_port_instance,
    get_input_port_instance,
    get_input_port_instances_for_component_instance,
    update_input_port_instance,
)
from ada_backend.repositories.output_port_instance_repository import get_output_port_instance_by_name
from ada_backend.repositories.port_mapping_repository import (
    delete_port_mapping_for_target_input,
    delete_port_mappings_for_graph,
    get_input_port_definition_id,
    get_output_port_definition_id,
    get_port_definition_by_id,
    insert_port_mapping,
    insert_port_mapping_with_output_instance,
)
from ada_backend.schemas.parameter_schema import ParameterKind
from ada_backend.schemas.pipeline.graph_schema import (
    GraphUpdateResponse,
    GraphUpdateSchema,
    SaveComponentInstanceResult,
)
from ada_backend.segment_analytics import track_project_saved
from ada_backend.services.agent_runner_service import get_agent_for_project
from ada_backend.services.errors import GraphNotBoundToProjectError
from ada_backend.services.graph.delete_graph_service import delete_component_instances_from_nodes
from ada_backend.services.graph.output_port_instance_sync import sync_output_port_instances_from_schema
from ada_backend.services.graph.playground_utils import (
    extract_playground_configuration,
    extract_playground_schema_from_component,
)
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance
from ada_backend.services.pipeline.update_pipeline_service import create_or_update_component_instance
from engine.field_expressions.ast import ExpressionNode, RefNode
from engine.field_expressions.errors import FieldExpressionError, FieldExpressionParseError
from engine.field_expressions.parser import parse_expression_flexible
from engine.field_expressions.serializer import to_json as expr_to_json
from engine.field_expressions.traversal import get_pure_ref, select_nodes

LOGGER = logging.getLogger(__name__)


def _sort_dict_keys_recursively(obj):
    """
    Recursively sort dictionary keys in a data structure.
    This ensures that dictionaries with the same content but different key orders
    produce the same JSON representation.
    """
    if isinstance(obj, dict):
        return {k: _sort_dict_keys_recursively(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [_sort_dict_keys_recursively(item) for item in obj]
    else:
        return obj


def _calculate_graph_hash(graph_project: GraphUpdateSchema) -> str:
    graph_dict = graph_project.model_dump(mode="json", exclude={"port_mappings"})
    sorted_dict = _sort_dict_keys_recursively(graph_dict)
    json_str = json.dumps(sorted_dict, sort_keys=True, separators=(",", ":"))
    hash_obj = hashlib.sha256(json_str.encode("utf-8"))
    return hash_obj.hexdigest()


def _calculate_graph_hash_from_db(session: Session, graph_runner_id: UUID) -> str:
    """Compute a stable hash of the full graph state from DB.

    Used as the canonical fingerprint across all save paths (full graph update,
    single instance save, delete) so that modification_hash values are always
    comparable and deduplication in update_graph_with_history_service works
    correctly regardless of which path last wrote a history entry.

    # TODO: This is a temporary fix. We will have modification history at the
    # component instance level.
    """
    results = (
        session.query(db.ComponentInstance, db.GraphRunnerNode)
        .join(db.GraphRunnerNode, db.ComponentInstance.id == db.GraphRunnerNode.node_id)
        .filter(db.GraphRunnerNode.graph_runner_id == graph_runner_id)
        .all()
    )

    nodes_repr = []
    for component_instance, graph_runner_node in results:
        params_repr = sorted(
            [
                {
                    "param_def_id": str(bp.parameter_definition_id),
                    "value": bp.value,
                    "secret_id": str(bp.organization_secret_id) if bp.organization_secret_id else None,
                    "order": bp.order,
                }
                for bp in component_instance.basic_parameters
            ],
            key=lambda x: x["param_def_id"],
        )
        nodes_repr.append(
            {
                "id": str(component_instance.id),
                "component_version_id": str(component_instance.component_version_id),
                "name": component_instance.name,
                "is_start_node": graph_runner_node.is_start_node,
                "parameters": params_repr,
            }
        )
    nodes_repr.sort(key=lambda x: x["id"])

    edges = get_edges(session, graph_runner_id)
    edges_repr = sorted(
        [
            {
                "id": str(e.id),
                "origin": str(e.source_node_id),
                "destination": str(e.target_node_id),
                "order": e.order,
            }
            for e in edges
        ],
        key=lambda x: x["id"],
    )

    graph_repr = {"nodes": nodes_repr, "edges": edges_repr}
    json_str = json.dumps(_sort_dict_keys_recursively(graph_repr), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def resolve_component_version_id_from_instance_id(session: Session, instance_id: UUID) -> UUID:
    """Resolve component version ID from a component instance ID"""
    instance = get_component_instance_by_id(session, instance_id)
    if not instance:
        raise ValueError(f"Component instance {instance_id} not found")
    return instance.component_version_id


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
        GraphNotBoundToProjectError: If the graph runner is not bound to any project
        ValueError: If the graph runner is not in draft mode
    """
    env_relationship = get_env_relationship_by_graph_runner_id(session, graph_runner_id)
    if not env_relationship:
        raise GraphNotBoundToProjectError(graph_runner_id)

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


def _ensure_graph_exists_and_validate(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    env: Optional[EnvType] = None,
    bypass_validation: bool = False,
) -> None:
    """
    Ensure the graph runner exists (create if needed) and validate it's in draft mode.

    Args:
        session: Database session
        graph_runner_id: ID of the graph runner
        project_id: ID of the project
        env: Environment type (defaults to DRAFT if not provided)
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


async def update_graph_with_history_service(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    graph_project: GraphUpdateSchema,
    env: Optional[EnvType] = None,
    user_id: UUID = None,
    bypass_validation: bool = False,
) -> GraphUpdateResponse:
    # Check if graph exists and validate draft mode BEFORE history modification check
    _ensure_graph_exists_and_validate(session, graph_runner_id, project_id, env, bypass_validation)

    current_hash = _calculate_graph_hash(graph_project)
    latest_history = get_latest_modification_history(session, graph_runner_id)
    previous_hash = latest_history.modification_hash if latest_history else None

    has_changed = previous_hash is None or current_hash != previous_hash

    if not has_changed:
        LOGGER.info(f"Graph {graph_runner_id} hash unchanged, skipping updates")
        playground_input_schema, playground_field_types = extract_playground_configuration(session, graph_runner_id)
        return GraphUpdateResponse(
            graph_id=graph_runner_id,
            playground_input_schema=playground_input_schema,
            playground_field_types=playground_field_types,
        )

    modification_history = None

    graph_update_response = await update_graph_service(
        session, graph_runner_id, project_id, graph_project, env, user_id, bypass_validation, skip_validation=True
    )

    if has_changed:
        modification_history = insert_modification_history(session, graph_runner_id, user_id, current_hash)
        LOGGER.info(f"Logged modification history for graph {graph_runner_id} by user {user_id or 'unknown'}")

    if modification_history:
        graph_update_response.last_edited_time = modification_history.created_at
        graph_update_response.last_edited_user_id = modification_history.user_id
        return graph_update_response
    else:
        return graph_update_response


# TODO: Refactor to rollback if instantiation failed.
async def update_graph_service(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    graph_project: GraphUpdateSchema,
    env: Optional[EnvType] = None,
    user_id: UUID = None,
    bypass_validation: bool = False,
    skip_validation: bool = False,
) -> GraphUpdateResponse:
    """
    Creates or updates a complete graph runner including all component instances,
    their parameters, and relationships.

    Args:
        bypass_validation: If True, skip draft mode validation (use for seeding/migrations only)
        skip_validation: If True, skip the validation check entirely (use when validation already done)
    """
    if not skip_validation:
        _ensure_graph_exists_and_validate(session, graph_runner_id, project_id, env, bypass_validation)

    # TODO: Add the get_graph_runner_nodes function when we will handle nested graphs
    previous_graph_nodes = set(node.id for node in get_component_nodes(session, graph_runner_id))
    previous_edge_ids = set(edge.id for edge in get_edges(session, graph_runner_id))

    # Create/update all component instances
    instance_ids = set()
    input_params_by_instance: dict[UUID, list] = defaultdict(list)
    for instance in graph_project.component_instances:
        parameter_params = []
        for param in instance.parameters:
            kind = getattr(param, "kind", ParameterKind.PARAMETER)
            if kind == ParameterKind.INPUT:
                if not instance.id:
                    raise ValueError(
                        f"Component instance ID is required for input parameters. Instance: {instance}, param: {param}"
                    )
                input_params_by_instance[instance.id].append(param)
            else:
                parameter_params.append(param)
        instance.parameters = parameter_params

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
        param_defs = get_component_parameter_definition_by_component_version(session, parent.component_version_id)
        param_def = next((p for p in param_defs if p.name == relation.parameter_name), None)
        if not param_def:
            raise ValueError(
                f"Parameter '{relation.parameter_name}' not found in "
                f"component definitions for component version '{parent.component_version_id}'"
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

    # Apply field expressions / input port instances for each instance
    for instance in graph_project.component_instances:
        _apply_instance_ports_and_expressions(
            session=session,
            graph_runner_id=graph_runner_id,
            instance=instance,
            instance_id=instance.id,
            input_params=input_params_by_instance.get(instance.id, []),
            all_instance_ids=instance_ids,
        )

    nodes_to_delete = previous_graph_nodes - instance_ids
    if len(nodes_to_delete) > 0:
        delete_component_instances_from_nodes(session, nodes_to_delete)

    # TODO: could use a bulk delete to avoid N+1 here
    for node_id in nodes_to_delete:
        delete_node(session, node_id)
    LOGGER.info("Deleted nodes: {}".format(len(nodes_to_delete)))

    agent = await get_agent_for_project(
        session,
        project_id=project_id,
        graph_runner_id=graph_runner_id,
    )
    await agent.close()
    if user_id:
        track_project_saved(user_id, project_id)

    playground_input_schema, playground_field_types = extract_playground_configuration(session, graph_runner_id)

    return GraphUpdateResponse(
        graph_id=graph_runner_id,
        playground_input_schema=playground_input_schema,
        playground_field_types=playground_field_types,
    )


def _apply_instance_ports_and_expressions(
    session: Session,
    graph_runner_id: UUID,
    instance,
    instance_id: UUID,
    input_params: list,
    all_instance_ids: Optional[set] = None,
) -> None:
    """Apply input_port_instances and INPUT params (as field expressions) for a single instance.

    This is the per-instance portion of the field-expression wiring logic. It:
    - Creates/updates input port instances from instance.input_port_instances.
    - Converts parameters with kind=INPUT into field expressions.
    - Deletes input port instances that are no longer referenced.
    """
    db_port_instances: dict[str, UUID] = {}
    port_instances = get_input_port_instances_for_component_instance(session, instance_id)
    for port in port_instances:
        if port.field_expression_id:
            db_port_instances[port.name] = port.id

    incoming_fields: set[str] = set()

    if instance.input_port_instances:
        for port_instance in instance.input_port_instances:
            if port_instance.field_expression and port_instance.field_expression.expression_json:
                field_name = port_instance.name
                incoming_fields.add(field_name)

                expr = create_field_expression(session, port_instance.field_expression.expression_json)
                existing_port_id = db_port_instances.get(field_name)
                if existing_port_id:
                    update_input_port_instance(session, existing_port_id, field_expression_id=expr.id)
                else:
                    create_input_port_instance(
                        session=session,
                        component_instance_id=instance.id,
                        name=field_name,
                        field_expression_id=expr.id,
                    )

    # Convert parameters with kind=INPUT into field expressions.
    # TODO: this mixes API-level `kind="input"` with service-level types; needs decoupling.
    for param in input_params:
        if not instance.id:
            raise ValueError(
                f"Component instance ID is required for input parameters. Instance: {instance}, param: {param}"
            )
        if all_instance_ids is not None and instance.id not in all_instance_ids:
            raise ValueError(f"Invalid field expression target: component instance {instance.id} not in update")

        field_name = param.name

        if param.value is None or param.value == "":
            LOGGER.warning(
                f"No expression value for input parameter {field_name} on instance {instance.id}, skipping"
            )
            sync_output_port_instances_from_schema(
                session=session,
                component_instance_id=instance.id,
                component_version_id=instance.component_version_id,
                field_name=field_name,
                value=None,
            )
            continue

        if field_name in incoming_fields:
            LOGGER.warning(
                f"Field expression {field_name} already exists for instance {instance.id}, skipping update"
            )
            continue

        incoming_fields.add(field_name)

        try:
            ast = parse_expression_flexible(param.value)
            LOGGER.debug(f"Parsed expression for {field_name}: {param.value}")
        except FieldExpressionParseError:
            LOGGER.error(f"Failed to parse field expression from parameter input: {param.value}")
            raise

        _validate_expression_references(session, graph_runner_id, ast)

        expression_json = expr_to_json(ast)

        existing_port_id = db_port_instances.get(field_name)
        if existing_port_id:
            port = get_input_port_instance(session, existing_port_id)
            if port and port.field_expression_id:
                update_field_expression(session, port.field_expression_id, expression_json)
            else:
                expr = create_field_expression(session, expression_json)
                update_input_port_instance(session, existing_port_id, field_expression_id=expr.id)
        else:
            expr = create_field_expression(session, expression_json)
            create_input_port_instance(
                session=session,
                component_instance_id=instance.id,
                name=field_name,
                field_expression_id=expr.id,
            )

        sync_output_port_instances_from_schema(
            session=session,
            component_instance_id=instance.id,
            component_version_id=instance.component_version_id,
            field_name=field_name,
            value=param.value,
        )

        ref_node = get_pure_ref(ast)
        if ref_node is not None:
            _create_port_mappings_for_pure_ref_expressions(
                session=session,
                graph_runner_id=graph_runner_id,
                component_instance_id=instance.id,
                field_name=field_name,
                ref_node=ref_node,
            )

    # Delete input port instances that are no longer referenced
    existing_fields = set(db_port_instances.keys())
    fields_to_delete = existing_fields - incoming_fields
    for field_name in fields_to_delete:
        port_id = db_port_instances[field_name]
        delete_input_port_instance(session, port_id)


async def save_component_instance_service(
    session: Session,
    project_id: UUID,
    graph_runner_id: UUID,
    instance,
    user_id: UUID,
) -> SaveComponentInstanceResult:
    """Update a single component instance and its field expressions / input ports.

    Edges are never touched here — edge management is done via addEdge / deleteEdge.
    Returns the saved instance ID and the full read representation of the instance.
    """
    _ensure_graph_exists_and_validate(session, graph_runner_id, project_id)

    # Split parameters into regular vs kind=INPUT
    input_params: list = []
    regular_params: list = []
    for param in instance.parameters:
        kind = getattr(param, "kind", ParameterKind.PARAMETER)
        if kind == ParameterKind.INPUT:
            if not instance.id:
                raise ValueError(
                    f"Component instance ID is required for input parameters. Instance: {instance}, param: {param}"
                )
            input_params.append(param)
        else:
            regular_params.append(param)
    instance.parameters = regular_params

    instance_id = create_or_update_component_instance(session, instance, project_id)
    upsert_component_node(
        session,
        graph_runner_id=graph_runner_id,
        component_instance_id=instance.id,
        is_start_node=instance.is_start_node,
    )

    _apply_instance_ports_and_expressions(
        session=session,
        graph_runner_id=graph_runner_id,
        instance=instance,
        instance_id=instance_id,
        input_params=input_params,
    )

    modification_hash = _calculate_graph_hash_from_db(session, graph_runner_id)
    insert_modification_history(session, graph_runner_id, user_id, modification_hash)
    LOGGER.info(f"Saved component instance {instance_id} in graph {graph_runner_id}")

    component_instance_read = get_component_instance(session, instance_id, is_start_node=instance.is_start_node)

    return SaveComponentInstanceResult(
        component_instance_id=instance_id,
        component_instance=component_instance_read,
    )


def delete_component_instance_service(
    session: Session,
    graph_runner_id: UUID,
    instance_id: UUID,
    user_id: UUID,
) -> dict:
    """Remove a component instance from a graph runner.

    Deletes all edges connected to the instance first, then removes the node
    from the graph runner and deletes the component instance itself.

    Returns a dict with ``instance_id`` and ``deleted_edge_ids`` so the
    caller can update the canvas without a full graph refetch.
    """
    validate_graph_is_draft(session, graph_runner_id)

    # Collect and delete all edges touching this instance before removing the node
    connected_edges = get_edges_for_instance_node(session, instance_id)
    deleted_edge_ids: list[UUID] = []
    for edge in connected_edges:
        delete_edge(session, edge.id)
        deleted_edge_ids.append(edge.id)

    delete_node(session, instance_id)
    delete_component_instances_from_nodes(session, {instance_id})

    modification_hash = _calculate_graph_hash_from_db(session, graph_runner_id)
    insert_modification_history(session, graph_runner_id, user_id, modification_hash)
    LOGGER.info(
        f"Deleted component instance {instance_id} from graph {graph_runner_id}; "
        f"deleted {len(deleted_edge_ids)} edge(s)"
    )

    return {"instance_id": instance_id, "deleted_edge_ids": deleted_edge_ids}


def add_edge_service(
    session: Session,
    graph_runner_id: UUID,
    edge_id: UUID,
    source_node_id: UUID,
    target_node_id: UUID,
    order: Optional[int] = None,
) -> UUID:
    """Create or update an edge between two component instance nodes."""
    if graph_runner_exists(session, source_node_id) or graph_runner_exists(session, target_node_id):
        raise ValueError("Nested graphs are not supported")
    upsert_edge(
        session,
        id=edge_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        graph_runner_id=graph_runner_id,
        order=order,
    )
    return edge_id


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
            source_component_version_id = resolve_component_version_id_from_instance_id(
                session, pm_schema.source_instance_id
            )
            target_component_version_id = resolve_component_version_id_from_instance_id(
                session, pm_schema.target_instance_id
            )

            # Resolve port names to port definition IDs
            source_port_def_id = get_output_port_definition_id(
                session, source_component_version_id, pm_schema.source_port_name
            )
            if not source_port_def_id:
                raise ValueError(
                    f"Output port '{pm_schema.source_port_name}' not found for component {source_component_version_id}"
                )

            target_port_def_id = get_input_port_definition_id(
                session, target_component_version_id, pm_schema.target_port_name
            )
            if not target_port_def_id:
                raise ValueError(
                    f"Input port '{pm_schema.target_port_name}' not found for component {target_component_version_id}"
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

    instance_to_component_version: dict[UUID, UUID] = {}
    for inst in graph_project.component_instances:
        if inst.id and inst.component_version_id:
            instance_to_component_version[inst.id] = inst.component_version_id

    missing_instance_ids = {iid for pair in unmapped_edges for iid in pair if iid not in instance_to_component_version}
    if missing_instance_ids:
        db_instances = get_component_instances_by_ids(session, list(missing_instance_ids))
        for iid, db_inst in db_instances.items():
            instance_to_component_version[iid] = db_inst.component_version_id

    component_version_ids = list(
        {instance_to_component_version[s] for s, t in unmapped_edges}
        | {instance_to_component_version[t] for s, t in unmapped_edges}
    )
    canonical_ports_by_component = get_canonical_ports_for_component_versions(session, component_version_ids)

    auto_generated_mappings: list[db.PortMapping] = []
    for source_instance_id, target_instance_id in unmapped_edges:
        if (
            source_instance_id not in instance_to_component_version
            or target_instance_id not in instance_to_component_version
        ):
            raise ValueError(
                "Unable to infer component ids for one or more unmapped edges; please provide explicit port_mappings."
            )

        source_component_version_id = instance_to_component_version[source_instance_id]
        target_component_version_id = instance_to_component_version[target_instance_id]

        source_ports = canonical_ports_by_component.get(source_component_version_id, {})
        target_ports = canonical_ports_by_component.get(target_component_version_id, {})

        source_port_name = source_ports.get("output") or "output"
        target_port_name = target_ports.get("input") or "input"

        # Resolve port names to port definition IDs
        source_port_def_id = get_output_port_definition_id(session, source_component_version_id, source_port_name)
        if not source_port_def_id:
            raise ValueError(f"Output port '{source_port_name}' not found for component {source_component_version_id}")

        target_port_def_id = get_input_port_definition_id(session, target_component_version_id, target_port_name)
        if not target_port_def_id:
            raise ValueError(f"Input port '{target_port_name}' not found for component {target_component_version_id}")

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


def _create_port_mappings_for_pure_ref_expressions(
    session: Session,
    graph_runner_id: UUID,
    component_instance_id: UUID,
    field_name: str,
    ref_node: RefNode,
) -> None:
    """
    Create a port mapping when the expression is a pure reference.
    Skip mapping creation for non-ref (literal/concat/multi-ref) expressions.
    This will be harmonized with port mappings later.
    """
    source_component_version_id = resolve_component_version_id_from_instance_id(session, UUID(ref_node.instance))
    target_component_version_id = resolve_component_version_id_from_instance_id(session, component_instance_id)

    source_instance_uuid = UUID(ref_node.instance)
    source_port_def_id = get_output_port_definition_id(session, source_component_version_id, ref_node.port)

    target_port_def_id = get_input_port_definition_id(session, target_component_version_id, field_name)
    if not target_port_def_id:
        LOGGER.warning(
            msg=f"Input port '{field_name}' not found for component "
            f"{target_component_version_id}, skipping port mapping"
        )
        return

    if source_port_def_id:
        validate_port_definition_types(session, source_port_def_id, target_port_def_id)

        # Ensure only one mapping exists for this target input
        delete_port_mapping_for_target_input(
            session=session,
            graph_runner_id=graph_runner_id,
            target_instance_id=component_instance_id,
            target_port_definition_id=target_port_def_id,
        )

        insert_port_mapping(
            session=session,
            graph_runner_id=graph_runner_id,
            source_instance_id=source_instance_uuid,
            source_port_definition_id=source_port_def_id,
            target_instance_id=component_instance_id,
            target_port_definition_id=target_port_def_id,
            dispatch_strategy="direct",
        )
        LOGGER.info(
            f"Created port mapping for {ref_node.instance}.{ref_node.port} -> {component_instance_id}.{field_name}"
        )
    else:
        # Static output port not found; check for a dynamic OutputPortInstance
        output_port_instance = get_output_port_instance_by_name(session, source_instance_uuid, ref_node.port)
        if not output_port_instance:
            available = get_output_ports_for_component_version(session, source_component_version_id)
            available_names = [p.name for p in available]
            LOGGER.warning(
                "[save] pure ref port mapping skipped: output port '%s' not found for component %s "
                "(ref %s.%s -> %s.%s). Available static output ports: %s",
                ref_node.port,
                source_component_version_id,
                ref_node.instance,
                ref_node.port,
                component_instance_id,
                field_name,
                available_names if available_names else "(none)",
            )
            return

        # Ensure only one mapping exists for this target input
        delete_port_mapping_for_target_input(
            session=session,
            graph_runner_id=graph_runner_id,
            target_instance_id=component_instance_id,
            target_port_definition_id=target_port_def_id,
        )

        insert_port_mapping_with_output_instance(
            session=session,
            graph_runner_id=graph_runner_id,
            source_instance_id=source_instance_uuid,
            source_output_port_instance_id=output_port_instance.id,
            target_instance_id=component_instance_id,
            target_port_definition_id=target_port_def_id,
            dispatch_strategy="direct",
        )
        LOGGER.info(
            f"Created dynamic port mapping for {ref_node.instance}.{ref_node.port} "
            f"(OutputPortInstance) -> {component_instance_id}.{field_name}"
        )


def _validate_expression_references(session: Session, graph_runner_id: UUID, ast: ExpressionNode) -> None:
    """Perform static validation of expression references at save-time.

    - Instance IDs must be valid UUIDs and exist in DB.
    - Referenced output ports must exist on the source component version.
    - For start nodes, also accepts input fields from payload_schema.
    """

    ref_nodes: Iterator[RefNode] = select_nodes(ast, lambda n: isinstance(n, RefNode))
    for ref_node in ref_nodes:
        try:
            source_instance_uuid = UUID(ref_node.instance)
        except Exception:
            raise FieldExpressionError(
                f"Invalid referenced instance id in expression: '{ref_node.instance}' is not a UUID",
            )

        source_instance = get_component_instance_by_id(session, source_instance_uuid)
        if not source_instance:
            raise FieldExpressionError(f"Referenced component instance not found: {ref_node.instance}")

        source_component_version_id = resolve_component_version_id_from_instance_id(session, source_instance_uuid)

        is_start = is_start_node(session, graph_runner_id, source_instance_uuid)

        # TODO: remove this once start node output ports are supported
        if is_start:
            try:
                component_instance_schema = get_component_instance(session, source_instance_uuid, is_start_node=True)
                playground_schema = extract_playground_schema_from_component(component_instance_schema)
                if playground_schema and ref_node.port in playground_schema and ref_node.port != "messages":
                    continue  # Valid start node input field
            except Exception:
                LOGGER.warning(
                    f"Could not retrieve playground schema for start node {source_instance_uuid}. "
                    "Falling back to output port validation.",
                    exc_info=True,
                )
                pass  # If we can't get the schema, fall through to check output ports

            source_port_def_id = get_output_port_definition_id(session, source_component_version_id, ref_node.port)
            if not source_port_def_id:
                # Also accept dynamic output port instances on the start node
                output_port_instance = get_output_port_instance_by_name(session, source_instance_uuid, ref_node.port)
                if not output_port_instance:
                    raise FieldExpressionError(
                        f"Port '{ref_node.port}' not found for start node '{source_component_version_id}' "
                        f"(checked input fields, static output ports, and dynamic output port instances)"
                    )
        else:
            source_port_def_id = get_output_port_definition_id(session, source_component_version_id, ref_node.port)
            if not source_port_def_id:
                # Also accept dynamic output port instances (e.g. keys from drives_output_schema)
                output_port_instance = get_output_port_instance_by_name(session, source_instance_uuid, ref_node.port)
                if not output_port_instance:
                    raise FieldExpressionError(
                        f"Output port '{ref_node.port}' not found for component version "
                        f"'{source_component_version_id}' (checked static output ports "
                        "and dynamic output port instances)"
                    )
