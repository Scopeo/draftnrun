import logging
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.component_repository import (
    delete_component_instances,
    get_component_instance_by_id,
)
from ada_backend.repositories.edge_repository import delete_edge, get_edges
from ada_backend.repositories.field_expression_repository import (
    delete_field_expression,
    get_field_expressions_for_instances,
    get_input_port_dependents_referencing_instance,
    update_field_expression,
    upsert_field_expression,
)
from ada_backend.repositories.graph_runner_repository import (
    delete_node,
    get_component_nodes,
    graph_runner_exists,
    upsert_component_node,
)
from ada_backend.repositories.input_port_instance_repository import (
    delete_input_port_instance,
    get_input_port_instances_for_component_instance,
)
from ada_backend.repositories.port_mapping_repository import (
    delete_port_mappings_involving_instance,
)
from ada_backend.schemas.parameter_schema import ParameterKind
from ada_backend.schemas.pipeline.component_instance_schema import (
    ComponentInstanceDeleteResponse,
    ComponentInstanceUpdateResponse,
    ComponentInstanceUpdateSchema,
)
from ada_backend.services.errors import (
    ComponentInstanceHasDependentExpressionsError,
    ComponentInstanceNotFound,
    ComponentInstanceNotInGraphError,
    GraphNotFound,
)
from ada_backend.services.graph.update_graph_service import (
    _create_port_mappings_for_pure_ref_expressions,
    _validate_expression_references,
    validate_graph_is_draft,
)
from ada_backend.services.pipeline.update_pipeline_service import create_or_update_component_instance
from engine.field_expressions.errors import FieldExpressionParseError
from engine.field_expressions.parser import parse_expression_flexible
from engine.field_expressions.serializer import to_json as expr_to_json
from engine.field_expressions.traversal import get_pure_ref

LOGGER = logging.getLogger(__name__)

EMPTY_EXPRESSION_JSON = {"type": "literal", "value": ""}


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
        raise GraphNotFound(graph_runner_id)

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

    instance_id = create_or_update_component_instance(session, component_data, project_id)
    upsert_component_node(
        session,
        graph_runner_id=graph_runner_id,
        component_instance_id=component_data.id,
        is_start_node=component_data.is_start_node,
    )

    db_field_expressions = set()
    existing_expressions = get_field_expressions_for_instances(session, [component_data.id])
    for expr in existing_expressions:
        db_field_expressions.add(expr.field_name)

    incoming_field_expressions = set()

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

        try:
            ast = parse_expression_flexible(param.value)
            LOGGER.debug(f"Parsed expression for {field_name}: {param.value}")
        except FieldExpressionParseError:
            LOGGER.error(f"Failed to parse field expression from parameter input: {param.value}")
            raise

        _validate_expression_references(session, graph_runner_id, ast)

        upsert_field_expression(
            session=session,
            component_instance_id=component_data.id,
            field_name=field_name,
            expression_json=expr_to_json(ast),
        )

        ref_node = get_pure_ref(ast)
        if ref_node is not None:
            _create_port_mappings_for_pure_ref_expressions(
                session=session,
                graph_runner_id=graph_runner_id,
                component_instance_id=component_data.id,
                field_name=field_name,
                ref_node=ref_node,
            )

    fields_to_delete = db_field_expressions - incoming_field_expressions
    for field_name in fields_to_delete:
        delete_field_expression(session, component_data.id, field_name)
        LOGGER.debug(f"Deleted field expression {field_name} from instance {component_data.id}")

    session.commit()

    return ComponentInstanceUpdateResponse(
        component_instance_id=instance_id,
        graph_runner_id=graph_runner_id,
        last_edited_time=datetime.utcnow(),
        last_edited_user_id=user_id,
    )


def _cascade_clear_field_expressions_referencing_instance(
    session: Session,
    graph_runner_id: UUID,
    component_instance_id: UUID,
) -> None:
    """Cleanup field expressions that reference the given instance.

    For each dependent InputPortInstance:
    - rewrite the stored FieldExpression to an empty literal (LiteralNode(""))
    - delete the InputPortInstance itself (so the broken input slot disappears)
    """
    dependents = get_input_port_dependents_referencing_instance(session, graph_runner_id, component_instance_id)
    for target_instance_id, field_name in dependents:
        ports = get_input_port_instances_for_component_instance(
            session, target_instance_id, eager_load_field_expression=True
        )
        for port in ports:
            if port.name == field_name and port.field_expression_id:
                update_field_expression(session, port.field_expression_id, EMPTY_EXPRESSION_JSON)
                LOGGER.debug(
                    "Cleared field expression %s on instance %s (referenced deleted instance %s)",
                    field_name,
                    target_instance_id,
                    component_instance_id,
                )
                delete_input_port_instance(session, port.id)
                break


def delete_component_instance_service(
    session: Session,
    graph_runner_id: UUID,
    component_instance_id: UUID,
    force: bool = False,
) -> ComponentInstanceDeleteResponse:
    if not graph_runner_exists(session, graph_runner_id):
        raise GraphNotFound(graph_runner_id)

    validate_graph_is_draft(session, graph_runner_id)

    component = get_component_instance_by_id(session, component_instance_id)
    if not component:
        raise ComponentInstanceNotFound(component_instance_id)

    graph_nodes = get_component_nodes(session, graph_runner_id)
    node_ids = {node.id for node in graph_nodes}
    if component_instance_id not in node_ids:
        raise ComponentInstanceNotInGraphError(component_instance_id, graph_runner_id)

    dependents = get_input_port_dependents_referencing_instance(session, graph_runner_id, component_instance_id)
    if dependents and not force:
        raise ComponentInstanceHasDependentExpressionsError(component_instance_id, dependents)

    if dependents and force:
        _cascade_clear_field_expressions_referencing_instance(session, graph_runner_id, component_instance_id)
        delete_port_mappings_involving_instance(session, graph_runner_id, component_instance_id)

    all_edges = get_edges(session, graph_runner_id)
    deleted_edge_ids = []

    for edge in all_edges:
        if edge.source_node_id == component_instance_id or edge.target_node_id == component_instance_id:
            delete_edge(session, edge.id)
            deleted_edge_ids.append(edge.id)
            LOGGER.info(f"Cascade deleted edge {edge.id} connected to component {component_instance_id}")

    delete_node(session, component_instance_id)
    LOGGER.info(f"Deleted component node {component_instance_id} from graph {graph_runner_id}")

    delete_component_instances(session, [component_instance_id])

    session.commit()

    return ComponentInstanceDeleteResponse(
        component_instance_id=component_instance_id,
        graph_runner_id=graph_runner_id,
        deleted_edge_ids=deleted_edge_ids,
        deleted_at=datetime.now(UTC),
    )
