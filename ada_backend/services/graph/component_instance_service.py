import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.component_repository import get_component_instance_by_id
from ada_backend.repositories.edge_repository import delete_edge, get_edges
from ada_backend.repositories.field_expression_repository import (
    delete_field_expression,
    get_field_expressions_for_instances,
    upsert_field_expression,
)
from ada_backend.repositories.graph_runner_repository import (
    delete_node,
    get_component_nodes,
    graph_runner_exists,
    upsert_component_node,
)
from ada_backend.repositories.port_mapping_repository import (
    delete_port_mapping_for_target_input,
    get_input_port_definition_id,
    get_output_port_definition_id,
    insert_port_mapping,
)
from ada_backend.schemas.parameter_schema import ParameterKind
from ada_backend.schemas.pipeline.component_instance_schema import (
    ComponentInstanceDeleteResponse,
    ComponentInstanceUpdateResponse,
    ComponentInstanceUpdateSchema,
)
from ada_backend.services.graph.update_graph_service import (
    _validate_expression_references,
    validate_graph_is_draft,
)
from ada_backend.services.pipeline.update_pipeline_service import create_or_update_component_instance
from engine.field_expressions.errors import FieldExpressionParseError
from engine.field_expressions.parser import parse_expression_flexible
from engine.field_expressions.serializer import to_json as expr_to_json
from engine.field_expressions.traversal import get_pure_ref

LOGGER = logging.getLogger(__name__)


def _create_port_mappings_for_pure_ref_expressions(
    session: Session,
    graph_runner_id: UUID,
    component_instance_id: UUID,
    field_name: str,
    ref_node,
) -> None:
    """
    For expressions like `ref("other_component.output_field")`, create port mappings.
    Deletes any existing port mappings for this target input first.
    """
    # Delete existing mappings for this target input
    target_port_def_id = get_input_port_definition_id(
        session,
        component_instance_id,
        field_name,
    )
    if target_port_def_id:
        delete_port_mapping_for_target_input(session, target_port_def_id, component_instance_id)

    # Create new mapping
    source_instance_id = UUID(ref_node.component_ref)
    source_field_name = ref_node.field

    source_port_def_id = get_output_port_definition_id(
        session,
        source_instance_id,
        source_field_name,
    )
    target_port_def_id = get_input_port_definition_id(
        session,
        component_instance_id,
        field_name,
    )

    if source_port_def_id and target_port_def_id:
        insert_port_mapping(
            session,
            source_instance_id=source_instance_id,
            source_port_definition_id=source_port_def_id,
            target_instance_id=component_instance_id,
            target_port_definition_id=target_port_def_id,
            dispatch_strategy="direct",
        )
        LOGGER.debug(
            f"Created port mapping: {source_instance_id}.{source_field_name} -> {component_instance_id}.{field_name}"
        )


async def upsert_component_instance_service(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    component_data: ComponentInstanceUpdateSchema,
    user_id: Optional[UUID] = None,
) -> ComponentInstanceUpdateResponse:
    """
    Creates or updates a single component instance within a graph.

    Args:
        session: Database session
        graph_runner_id: The graph this component belongs to
        project_id: The project this component belongs to
        component_data: Component instance data including parameters, field expressions, and port mappings
        user_id: User making the change (for tracking)

    Returns:
        ComponentInstanceUpdateResponse with the component instance ID and metadata

    Raises:
        ValueError: If graph doesn't exist, is not in draft mode, or validation fails
        GraphNotBoundToProjectError: If graph is not bound to the project
    """
    # Validate graph exists and is in draft mode
    if not graph_runner_exists(session, graph_runner_id):
        raise ValueError(f"Graph runner {graph_runner_id} not found")

    validate_graph_is_draft(session, graph_runner_id)

    # Separate INPUT kind parameters from regular parameters
    parameter_params = []
    input_params = []
    for param in component_data.parameters:
        kind = getattr(param, "kind", ParameterKind.PARAMETER)
        if kind == ParameterKind.INPUT:
            input_params.append(param)
        else:
            parameter_params.append(param)

    # Update the component data with only non-INPUT parameters
    component_data.parameters = parameter_params

    # Create or update the component instance
    instance_id = create_or_update_component_instance(session, component_data, project_id)

    # Upsert the graph runner node (links component to graph)
    upsert_component_node(
        session,
        graph_runner_id=graph_runner_id,
        component_instance_id=component_data.id,
        is_start_node=component_data.is_start_node,
    )

    # Process field expressions from INPUT parameters and explicit field_expressions
    db_field_expressions = set()
    existing_expressions = get_field_expressions_for_instances(session, [component_data.id])
    for expr in existing_expressions:
        db_field_expressions.add(expr.field_name)

    incoming_field_expressions = set()

    # Process INPUT kind parameters as field expressions
    for param in input_params:
        field_name = param.name

        if param.value is None or param.value == "":
            LOGGER.warning(
                f"No expression value for input parameter {field_name} on instance {component_data.id}, skipping"
            )
            continue

        if field_name in incoming_field_expressions:
            LOGGER.warning(
                f"Field expression {field_name} already exists for instance {component_data.id}, skipping update"
            )
            continue

        incoming_field_expressions.add(field_name)

        # Parse expression
        try:
            ast = parse_expression_flexible(param.value)
            LOGGER.debug(f"Parsed expression for {field_name}: {param.value}")
        except FieldExpressionParseError:
            LOGGER.error(f"Failed to parse field expression from parameter input: {param.value}")
            raise

        # Validate references point to components in the same graph
        _validate_expression_references(session, graph_runner_id, ast)

        # Save field expression
        upsert_field_expression(
            session=session,
            component_instance_id=component_data.id,
            field_name=field_name,
            expression_json=expr_to_json(ast),
        )

        # Create port mappings for pure ref expressions
        ref_node = get_pure_ref(ast)
        if ref_node is not None:
            _create_port_mappings_for_pure_ref_expressions(
                session=session,
                graph_runner_id=graph_runner_id,
                component_instance_id=component_data.id,
                field_name=field_name,
                ref_node=ref_node,
            )

    # Process explicit field expressions
    for field_expr in component_data.field_expressions:
        field_name = field_expr.field_name

        if field_name in incoming_field_expressions:
            LOGGER.warning(f"Field expression {field_name} already defined for instance {component_data.id}, skipping")
            continue

        incoming_field_expressions.add(field_name)

        # Parse expression
        try:
            ast = parse_expression_flexible(field_expr.expression_json)
            LOGGER.debug(f"Parsed field expression for {field_name}")
        except FieldExpressionParseError:
            LOGGER.error(f"Failed to parse field expression: {field_expr.expression_json}")
            raise

        # Validate references
        _validate_expression_references(session, graph_runner_id, ast)

        # Save field expression
        upsert_field_expression(
            session=session,
            component_instance_id=component_data.id,
            field_name=field_name,
            expression_json=expr_to_json(ast),
        )

        # Create port mappings for pure ref expressions
        ref_node = get_pure_ref(ast)
        if ref_node is not None:
            _create_port_mappings_for_pure_ref_expressions(
                session=session,
                graph_runner_id=graph_runner_id,
                component_instance_id=component_data.id,
                field_name=field_name,
                ref_node=ref_node,
            )

    # Delete field expressions that are no longer present
    fields_to_delete = db_field_expressions - incoming_field_expressions
    for field_name in fields_to_delete:
        delete_field_expression(session, component_data.id, field_name)
        LOGGER.debug(f"Deleted field expression {field_name} from instance {component_data.id}")

    # Process explicit port mappings
    for port_mapping in component_data.port_mappings:
        # Resolve port definition IDs
        source_port_def_id = get_output_port_definition_id(
            session,
            port_mapping.source_instance_id,
            port_mapping.source_port_name,
        )
        target_port_def_id = get_input_port_definition_id(
            session,
            port_mapping.target_instance_id,
            port_mapping.target_port_name,
        )

        if source_port_def_id and target_port_def_id:
            # Delete existing mapping for this target input
            delete_port_mapping_for_target_input(
                session,
                target_port_def_id,
                port_mapping.target_instance_id,
            )

            # Insert new mapping
            insert_port_mapping(
                session,
                source_instance_id=port_mapping.source_instance_id,
                source_port_definition_id=source_port_def_id,
                target_instance_id=port_mapping.target_instance_id,
                target_port_definition_id=target_port_def_id,
                dispatch_strategy=port_mapping.dispatch_strategy,
            )
            LOGGER.debug(
                f"Created port mapping: {port_mapping.source_instance_id}.{port_mapping.source_port_name} "
                f"-> {port_mapping.target_instance_id}.{port_mapping.target_port_name}"
            )

    session.commit()

    return ComponentInstanceUpdateResponse(
        component_instance_id=instance_id,
        graph_runner_id=graph_runner_id,
        last_edited_time=datetime.utcnow(),
        last_edited_user_id=user_id,
    )


def delete_component_instance_service(
    session: Session,
    graph_runner_id: UUID,
    component_instance_id: UUID,
) -> ComponentInstanceDeleteResponse:
    """
    Deletes a component instance from a graph and cascade deletes connected edges.

    Args:
        session: Database session
        graph_runner_id: The graph this component belongs to
        component_instance_id: The component instance to delete

    Returns:
        ComponentInstanceDeleteResponse with deleted IDs

    Raises:
        ValueError: If graph doesn't exist, is not in draft mode, or component not found
        GraphNotBoundToProjectError: If graph is not bound to the project
    """
    # Validate graph exists and is in draft mode
    if not graph_runner_exists(session, graph_runner_id):
        raise ValueError(f"Graph runner {graph_runner_id} not found")

    validate_graph_is_draft(session, graph_runner_id)

    # Verify component exists and is in this graph
    component = get_component_instance_by_id(session, component_instance_id)
    if not component:
        raise ValueError(f"Component instance {component_instance_id} not found")

    # Check if component is in this graph
    graph_nodes = get_component_nodes(session, graph_runner_id)
    node_ids = {node.id for node in graph_nodes}
    if component_instance_id not in node_ids:
        raise ValueError(f"Component instance {component_instance_id} is not in graph {graph_runner_id}")

    # Find and delete all edges connected to this component
    all_edges = get_edges(session, graph_runner_id)
    deleted_edge_ids = []

    for edge in all_edges:
        if edge.source_node_id == component_instance_id or edge.target_node_id == component_instance_id:
            delete_edge(session, edge.id)
            deleted_edge_ids.append(edge.id)
            LOGGER.info(f"Cascade deleted edge {edge.id} connected to component {component_instance_id}")

    # Delete the graph runner node (this unlinks the component from the graph)
    delete_node(session, component_instance_id)
    LOGGER.info(f"Deleted component node {component_instance_id} from graph {graph_runner_id}")

    # Note: We don't delete the ComponentInstance itself here because it might be referenced
    # in other graphs or relationships. The delete_component_instances_from_nodes function
    # in delete_graph_service.py handles that when the entire graph is deleted.

    session.commit()

    return ComponentInstanceDeleteResponse(
        component_instance_id=component_instance_id,
        graph_runner_id=graph_runner_id,
        deleted_edge_ids=deleted_edge_ids,
        deleted_at=datetime.utcnow(),
    )
