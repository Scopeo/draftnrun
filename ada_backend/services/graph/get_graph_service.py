from uuid import UUID
import logging

from sqlalchemy.orm import Session

from ada_backend.repositories.edge_repository import get_edges
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.repositories.graph_runner_repository import (
    get_component_nodes,
    graph_runner_exists,
)
from ada_backend.repositories.port_mapping_repository import list_port_mappings_for_graph
from ada_backend.schemas.pipeline.graph_schema import GraphGetResponse, EdgeSchema
from ada_backend.services.errors import GraphNotFound
from ada_backend.schemas.pipeline.port_mapping_schema import PortMappingSchema
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance, get_relationships

LOGGER = logging.getLogger(__name__)


def get_graph_service(
    session: Session,
    project_id: UUID,
    graph_runner_id: UUID,
) -> GraphGetResponse:
    if not graph_runner_exists(session, graph_runner_id):
        raise GraphNotFound(graph_runner_id)

    project_env_binding = get_env_relationship_by_graph_runner_id(session, graph_runner_id)
    if not project_env_binding:
        raise ValueError(f"Graph with ID {graph_runner_id} is not bound to any project.")
    if project_env_binding.project_id != project_id:
        raise ValueError(
            f"Graph with ID {graph_runner_id} is bound to project {project_env_binding.project_id}, not {project_id}."
        )

    # TODO: Add the get_graph_runner_nodes function when we will handle nested graphs
    component_nodes = get_component_nodes(session, graph_runner_id)

    component_instances_with_definitions = []
    relationships = []
    edges = []
    port_mappings = []

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

    return GraphGetResponse(
        component_instances=component_instances_with_definitions,
        relationships=relationships,
        edges=edges,
        tag_version=project_env_binding.graph_runner.tag_version,
        port_mappings=port_mappings,
    )
