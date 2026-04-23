import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.component_repository import (
    delete_sub_component_inputs_for_instance,
    get_component_instance_by_id,
)
from ada_backend.repositories.edge_repository import delete_edge, get_edges
from ada_backend.repositories.field_expression_repository import (
    create_field_expression,
    delete_field_expression_by_id,
    update_field_expression,
)
from ada_backend.repositories.graph_runner_repository import (
    delete_node,
    get_component_nodes,
    upsert_component_node,
)
from ada_backend.repositories.input_port_instance_repository import (
    create_input_port_instance,
    get_input_port_instances_for_component_instance,
    update_input_port_instance,
)
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.pipeline.graph_schema import (
    ComponentCreateV2Schema,
    ComponentUpdateV2Schema,
)
from ada_backend.services.graph.delete_graph_service import delete_component_instances_from_nodes
from ada_backend.services.pipeline.update_pipeline_service import (
    _normalize_expression_json,
    create_or_update_component_instance,
)

LOGGER = logging.getLogger(__name__)


def _to_component_instance_schema(
    instance_id: UUID | None,
    component_id: UUID,
    component_version_id: UUID,
    label: str | None,
    is_start_node: bool,
    parameters: list[dict],
    input_port_instances: list[dict],
    port_configurations: list[dict] | None,
    integration: dict | None,
    tool_description_override: str | None,
) -> ComponentInstanceSchema:
    return ComponentInstanceSchema(
        id=instance_id,
        name=label,
        is_start_node=is_start_node,
        component_id=component_id,
        component_version_id=component_version_id,
        parameters=parameters,
        input_port_instances=input_port_instances,
        port_configurations=port_configurations,
        integration=integration,
        tool_description_override=tool_description_override,
    )


def create_component_in_graph(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    payload: ComponentCreateV2Schema,
) -> UUID:
    instance_schema = _to_component_instance_schema(
        instance_id=None,
        component_id=payload.component_id,
        component_version_id=payload.component_version_id,
        label=payload.label,
        is_start_node=payload.is_start_node,
        parameters=payload.parameters,
        input_port_instances=payload.input_port_instances,
        port_configurations=payload.port_configurations,
        integration=payload.integration,
        tool_description_override=payload.tool_description_override,
    )
    instance_id = create_or_update_component_instance(session, instance_schema, project_id)
    upsert_component_node(
        session,
        graph_runner_id=graph_runner_id,
        component_instance_id=instance_id,
        is_start_node=payload.is_start_node,
    )
    return instance_id


def _sync_input_port_field_expressions(
    session: Session,
    instance_id: UUID,
    incoming_port_instances: list[dict],
) -> None:
    """Sync field expressions on input port instances for a single component.

    Creates, updates, or removes field expressions so the DB matches the
    incoming payload.  Mirrors the logic in ``update_graph_service`` but
    scoped to a single component instance (used by the V2 component PUT).
    """
    db_ports = get_input_port_instances_for_component_instance(
        session,
        instance_id,
        eager_load_field_expression=True,
    )
    db_port_by_name: dict[str, object] = {p.name: p for p in db_ports}

    incoming_names: set[str] = set()

    for port_data in incoming_port_instances:
        field_expr_data = port_data.get("field_expression")
        if not field_expr_data or not field_expr_data.get("expression_json"):
            continue

        field_name = port_data["name"]
        incoming_names.add(field_name)

        expression_json = _normalize_expression_json(field_expr_data["expression_json"])
        if expression_json is None:
            continue

        existing_port = db_port_by_name.get(field_name)
        if existing_port:
            if existing_port.field_expression_id:
                update_field_expression(session, existing_port.field_expression_id, expression_json)
            else:
                expr = create_field_expression(session, expression_json)
                update_input_port_instance(session, existing_port.id, field_expression_id=expr.id)
        else:
            expr = create_field_expression(session, expression_json)
            create_input_port_instance(
                session=session,
                component_instance_id=instance_id,
                name=field_name,
                field_expression_id=expr.id,
            )

    for port in db_ports:
        if port.name not in incoming_names and port.field_expression_id:
            delete_field_expression_by_id(session, port.field_expression_id)
            update_input_port_instance(session, port.id, field_expression_id=None)


def update_single_component(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    instance_id: UUID,
    payload: ComponentUpdateV2Schema,
) -> None:
    existing = get_component_instance_by_id(session, instance_id)
    if not existing:
        raise ValueError(f"Component instance {instance_id} not found")

    nodes = get_component_nodes(session, graph_runner_id)
    current_node = next((n for n in nodes if n.id == instance_id), None)
    if current_node is None:
        raise ValueError(f"Component instance {instance_id} does not belong to graph {graph_runner_id}")

    label = payload.label if payload.label is not None else existing.name
    is_start_node = payload.is_start_node if payload.is_start_node is not None else current_node.is_start_node

    instance_schema = _to_component_instance_schema(
        instance_id=instance_id,
        component_id=existing.component_version.component_id,
        component_version_id=existing.component_version_id,
        label=label,
        is_start_node=is_start_node,
        parameters=payload.parameters,
        input_port_instances=payload.input_port_instances,
        port_configurations=payload.port_configurations,
        integration=payload.integration,
        tool_description_override=payload.tool_description_override,
    )
    create_or_update_component_instance(session, instance_schema, project_id)

    if payload.input_port_instances:
        _sync_input_port_field_expressions(session, instance_id, payload.input_port_instances)

    upsert_component_node(
        session,
        graph_runner_id=graph_runner_id,
        component_instance_id=instance_id,
        is_start_node=is_start_node,
    )


def delete_component_from_graph(
    session: Session,
    graph_runner_id: UUID,
    instance_id: UUID,
) -> None:
    node_ids = {node.id for node in get_component_nodes(session, graph_runner_id)}
    if instance_id not in node_ids:
        raise ValueError(f"Component instance {instance_id} does not belong to graph {graph_runner_id}")

    edges = get_edges(session, graph_runner_id)
    for edge in edges:
        if edge.source_node_id == instance_id or edge.target_node_id == instance_id:
            delete_edge(session, edge.id)

    delete_sub_component_inputs_for_instance(session, instance_id)

    delete_component_instances_from_nodes(session, {instance_id})
    delete_node(session, instance_id)
