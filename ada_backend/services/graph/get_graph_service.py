from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ada_backend.repositories.edge_repository import get_edges
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.repositories.graph_runner_repository import (
    get_component_nodes,
    graph_runner_exists,
)
from ada_backend.schemas.pipeline.graph_schema import GraphGetResponse, EdgeSchema
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance, get_relationships

LOGGER = logging.getLogger(__name__)


async def get_graph_service(
    session: AsyncSession,
    project_id: UUID,
    graph_runner_id: UUID,
) -> GraphGetResponse:
    """
    Asynchronously retrieves a graph, including its component instances, relationships, and edges.
    """
    if not await graph_runner_exists(session, graph_runner_id):
        raise ValueError(f"Graph with ID {graph_runner_id} not found.")

    env_relationship = await get_env_relationship_by_graph_runner_id(session, graph_runner_id)
    if not env_relationship:
        raise ValueError(f"Graph with ID {graph_runner_id} is not bound to any project.")
    if env_relationship.project_id != project_id:
        raise ValueError(
            f"Graph with ID {graph_runner_id} is bound to project {env_relationship.project_id}, not {project_id}."
        )

    # TODO: Add the get_graph_runner_nodes function when we will handle nested graphs
    component_nodes = await get_component_nodes(session, graph_runner_id)

    component_instances_with_definitions = []
    relationships = []
    edges = []

    for component_node in component_nodes:
        component_instances_with_definitions.append(
            await get_component_instance(
                session,
                component_node.id,
                is_start_node=component_node.is_start_node,
            )
        )
        relationships += [
            rel
            for rel in await get_relationships(
                session,
                component_node.id,
            )
        ]

    graph_runner_edges = await get_edges(session, graph_runner_id)
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

    return GraphGetResponse(
        component_instances=component_instances_with_definitions,
        relationships=relationships,
        edges=edges,
    )
