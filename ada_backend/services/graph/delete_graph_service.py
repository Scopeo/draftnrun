from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ada_backend.repositories.component_repository import delete_component_instances
from ada_backend.repositories.graph_runner_repository import delete_graph_runner, get_component_nodes

LOGGER = logging.getLogger(__name__)


async def delete_component_instances_from_nodes(session: AsyncSession, component_node_ids: set[UUID]) -> None:
    """
    Deletes component instances from the database asynchronously.

    Args:
        session (AsyncSession): SQLAlchemy asynchronous session.
        component_node_ids (set[UUID]): Set of component instance IDs to delete.
    """
    await delete_component_instances(session, component_instance_ids=component_node_ids)
    LOGGER.info("Deleted instances: {}".format(len(component_node_ids)))


async def delete_graph_runner_service(session: AsyncSession, graph_runner_id: UUID):
    """
    Deletes a graph runner and all its associated nodes and edges asynchronously.

    Args:
        session (AsyncSession): SQLAlchemy asynchronous session.
        graph_runner_id (UUID): ID of the graph runner to delete.
    """
    graph_nodes = await get_component_nodes(session, graph_runner_id)
    await delete_graph_runner(session, graph_runner_id)

    # Delete all component instances associated with the graph runner
    await delete_component_instances_from_nodes(session, component_node_ids={node.id for node in graph_nodes})
