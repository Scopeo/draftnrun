from typing import Optional
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


async def get_edges(session: AsyncSession, graph_runner_id: UUID) -> list[db.GraphRunnerEdge]:
    """
    Retrieves the edges associated with a graph.

    Args:
        session (AsyncSession): Async SQLAlchemy session.
        graph_runner_id (UUID): ID of the graph whose edges to retrieve.

    Returns:
        list[db.GraphRunnerEdge]: List of GraphRunnerEdge objects.
    """
    result = await session.execute(
        select(db.GraphRunnerEdge).filter(db.GraphRunnerEdge.graph_runner_id == graph_runner_id)
    )
    return result.scalars().all()


async def upsert_edge(
    session: AsyncSession,
    id: UUID,
    source_node_id: UUID,
    target_node_id: UUID,
    graph_runner_id: Optional[UUID] = None,
    order: Optional[int] = None,
) -> None:
    """
    Creates or updates an edge.

    If the edge exists, updates its source and target (graph_runner_id remains unchanged).
    If not, creates a new edge with the given source, target, and required graph_runner_id.
    """
    result = await session.execute(select(db.GraphRunnerEdge).filter(db.GraphRunnerEdge.id == id))
    edge = result.scalar_one_or_none()

    if edge:
        edge.source_node_id = source_node_id
        edge.target_node_id = target_node_id
        edge.order = order
    elif graph_runner_id:
        edge = db.GraphRunnerEdge(
            id=id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            graph_runner_id=graph_runner_id,
            order=order,
        )
        session.add(edge)
    else:
        raise ValueError("Graph runner ID is required to create a new edge")

    await session.commit()


async def delete_edge(session: AsyncSession, id: UUID) -> None:
    result = await session.execute(select(db.GraphRunnerEdge).filter(db.GraphRunnerEdge.id == id))
    edge = result.scalar_one_or_none()

    if edge:
        LOGGER.info(f"Deleting edge with id {id}")
        await session.delete(edge)
        await session.commit()
    else:
        raise ValueError(f"Edge with id {id} not found")
