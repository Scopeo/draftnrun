import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import ParameterType, PortType
from ada_backend.repositories.component_repository import get_port_definitions_for_component_version_ids
from ada_backend.repositories.edge_repository import get_edges
from ada_backend.repositories.field_expression_repository import get_field_expressions_for_instances
from ada_backend.repositories.graph_runner_repository import (
    get_component_nodes,
    get_latest_modification_history,
)
from ada_backend.repositories.port_mapping_repository import list_port_mappings_for_graph
from ada_backend.schemas.parameter_schema import ParameterKind, PipelineParameterReadSchema
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionReadSchema
from ada_backend.schemas.pipeline.graph_schema import EdgeSchema, GraphGetResponse
from ada_backend.schemas.pipeline.port_mapping_schema import PortMappingSchema
from ada_backend.services.graph.graph_validation_utils import validate_graph_runner_belongs_to_project
from ada_backend.services.graph.playground_utils import (
    classify_schema_fields,
    extract_playground_schema_from_component,
)
from ada_backend.services.parameter_synthesis_utils import filter_conflicting_parameters
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance, get_relationships
from ada_backend.services.tag_service import compose_tag_name
from engine.field_expressions.parser import unparse_expression
from engine.field_expressions.serializer import from_json as expr_from_json

LOGGER = logging.getLogger(__name__)


def get_graph_service(
    session: Session,
    project_id: UUID,
    graph_runner_id: UUID,
) -> GraphGetResponse:
    project_env_binding = validate_graph_runner_belongs_to_project(session, graph_runner_id, project_id)

    # TODO: Add the get_graph_runner_nodes function when we will handle nested graphs
    component_nodes = get_component_nodes(session, graph_runner_id)

    component_instances_with_definitions = []
    relationships = []
    edges = []
    port_mappings = []
    field_expressions_by_instance: dict[UUID, list[FieldExpressionReadSchema]] = defaultdict(list)
    playground_input_schema = None

    for component_node in component_nodes:
        component_instance = get_component_instance(
            session,
            component_node.id,
            is_start_node=component_node.is_start_node,
        )
        component_instances_with_definitions.append(component_instance)

        if component_node.is_start_node and playground_input_schema is None:
            playground_input_schema = extract_playground_schema_from_component(component_instance)

        relationships += [
            rel
            for rel in get_relationships(
                session,
                component_node.id,
            )
        ]
    graph_runner_edges = get_edges(session, graph_runner_id)
    for edge in graph_runner_edges:
        edges.append(
            EdgeSchema(
                id=edge.id,
                origin=edge.source_node_id,
                destination=edge.target_node_id,
                order=edge.order,
            )
        )
        LOGGER.info(f"Edge from {edge.source_node_id} to {edge.target_node_id}")

    # Include port mappings at top-level so GET->PUT roundtrips
    pms = list_port_mappings_for_graph(session, graph_runner_id)
    for pm in pms:
        port_mappings.append(
            PortMappingSchema(
                source_instance_id=pm.source_instance_id,
                source_port_name=pm.source_port_definition.name,
                target_instance_id=pm.target_instance_id,
                target_port_name=pm.target_port_definition.name,
                dispatch_strategy=pm.dispatch_strategy,
            )
        )

    # Fetch field expressions
    component_instance_ids = [node.id for node in component_nodes]
    field_expression_records = get_field_expressions_for_instances(session, component_instance_ids)
    for expression in field_expression_records:
        field_expressions_by_instance[expression.component_instance_id].append(
            FieldExpressionReadSchema(
                field_name=expression.field_name,
                expression_json=expression.expression_json,
                expression_text=(
                    unparse_expression(expr_from_json(expression.expression_json))
                    if expression.expression_json
                    else None
                ),
            )
        )
    for comp_instance in component_instances_with_definitions:
        comp_instance.field_expressions = field_expressions_by_instance.get(comp_instance.id, [])

    # Synthesize input ports as parameters
    component_version_ids = list({ci.component_version_id for ci in component_instances_with_definitions})
    all_port_definitions = get_port_definitions_for_component_version_ids(session, component_version_ids)
    input_ports_by_component_version: dict[UUID, list] = defaultdict(list)
    for port in all_port_definitions:
        if port.port_type == PortType.INPUT:
            input_ports_by_component_version[port.component_version_id].append(port)

    for comp_instance in component_instances_with_definitions:
        field_expression_by_name = {fe.field_name: fe.expression_text for fe in comp_instance.field_expressions}
        input_ports = input_ports_by_component_version.get(comp_instance.component_version_id, [])

        comp_instance.parameters = filter_conflicting_parameters(comp_instance.parameters or [], input_ports)

        for input_port in input_ports:
            comp_instance.parameters.append(
                PipelineParameterReadSchema(
                    kind=ParameterKind.INPUT,
                    id=input_port.id,
                    name=input_port.name,
                    type=input_port.parameter_type or ParameterType.STRING,
                    nullable=True,
                    default=None,
                    ui_component=input_port.ui_component,
                    ui_component_properties=input_port.ui_component_properties,
                    is_advanced=False,
                    value=field_expression_by_name.get(input_port.name),
                )
            )

        # TODO: Temporary patch to ensure 'messages' appears first. Clean later.
        comp_instance.parameters.sort(
            key=lambda p: (
                0 if p.name == "messages" else 1,
                p.order if p.order is not None else 999,
                p.name,
            )
        )

    latest_modification_history = get_latest_modification_history(session, graph_runner_id)

    playground_field_types = None
    if playground_input_schema:
        playground_field_types = classify_schema_fields(playground_input_schema)

    # Build response, omitting change_log if unset (None)
    response = GraphGetResponse(
        component_instances=component_instances_with_definitions,
        relationships=relationships,
        edges=edges,
        port_mappings=port_mappings,
        tag_name=compose_tag_name(
            project_env_binding.graph_runner.tag_version,
            project_env_binding.graph_runner.version_name,
        ),
        change_log=project_env_binding.graph_runner.change_log,
        last_edited_time=latest_modification_history.created_at if latest_modification_history else None,
        last_edited_user_id=latest_modification_history.user_id if latest_modification_history else None,
        playground_input_schema=playground_input_schema,
        playground_field_types=playground_field_types,
    )
    return response
