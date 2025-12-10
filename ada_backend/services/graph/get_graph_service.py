from uuid import UUID
from collections import defaultdict
import logging

from sqlalchemy.orm import Session

from ada_backend.repositories.edge_repository import get_edges
from ada_backend.repositories.graph_runner_repository import (
    get_component_nodes,
    get_latest_modification_history,
)
from ada_backend.repositories.port_mapping_repository import list_port_mappings_for_graph
from ada_backend.repositories.field_expression_repository import get_field_expressions_for_instances
from ada_backend.schemas.pipeline.graph_schema import GraphGetResponse, EdgeSchema
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionReadSchema
from ada_backend.schemas.pipeline.port_mapping_schema import PortMappingSchema
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance, get_relationships
from ada_backend.services.graph.graph_validation_utils import validate_graph_runner_belongs_to_project
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

    for component_node in component_nodes:
        component_instances_with_definitions.append(
            get_component_instance(
                session,
                component_node.id,
                is_start_node=component_node.is_start_node,
            )
        )
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
    for ci in component_instances_with_definitions:
        ci.field_expressions = field_expressions_by_instance.get(ci.id, [])

    latest_modification_history = get_latest_modification_history(session, graph_runner_id)

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
    )
    return response
