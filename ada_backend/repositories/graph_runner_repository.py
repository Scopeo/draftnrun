from typing import Optional
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists
from sqlalchemy.sql import delete as sql_delete

from ada_backend.database import models as db
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.schemas.pipeline.graph_schema import ComponentNodeDTO
from ada_backend.repositories.utils import create_input_component

LOGGER = logging.getLogger(__name__)


async def get_graph_runners_by_project(session: AsyncSession, project_id: UUID) -> list[db.GraphRunner]:
    result = await session.execute(
        select(db.GraphRunner)
        .join(db.ProjectEnvironmentBinding, db.GraphRunner.id == db.ProjectEnvironmentBinding.graph_runner_id)
        .where(db.ProjectEnvironmentBinding.project_id == project_id)
    )
    return result.scalars().all()


async def get_graph_runner_for_env(
    session: AsyncSession, project_id: UUID, env: db.EnvType
) -> Optional[db.GraphRunner]:
    result = await session.execute(
        select(db.GraphRunner)
        .join(db.ProjectEnvironmentBinding, db.GraphRunner.id == db.ProjectEnvironmentBinding.graph_runner_id)
        .where(
            db.ProjectEnvironmentBinding.project_id == project_id,
            db.ProjectEnvironmentBinding.environment == env,
        )
    )
    return result.scalar_one_or_none()


async def insert_graph_runner(session: AsyncSession, graph_id: UUID, add_input: bool = False) -> db.GraphRunner:
    graph_runner = db.GraphRunner(id=graph_id)
    session.add(graph_runner)
    if add_input:
        await add_input_component_to_graph(session, graph_id)
    await session.commit()
    return graph_runner


async def insert_graph_runner_and_bind_to_project(
    session: AsyncSession,
    graph_id: UUID,
    project_id: UUID,
    env: Optional[db.EnvType] = None,
) -> None:
    graph_runner = db.GraphRunner(id=graph_id)
    graph_runner_relationship = db.ProjectEnvironmentBinding(
        project_id=project_id, graph_runner_id=graph_id, environment=env
    )
    session.add_all([graph_runner, graph_runner_relationship])
    await session.commit()


async def upsert_component_node(
    session: AsyncSession, graph_runner_id: UUID, component_instance_id: UUID, is_start_node: bool = False
) -> None:
    result = await session.execute(
        select(db.GraphRunnerNode).where(
            db.GraphRunnerNode.graph_runner_id == graph_runner_id,
            db.GraphRunnerNode.node_id == component_instance_id,
        )
    )
    node_to_graph_runner = result.scalar_one_or_none()

    if node_to_graph_runner:
        node_to_graph_runner.is_start_node = is_start_node
    else:
        node_to_graph_runner = db.GraphRunnerNode(
            node_id=component_instance_id,
            graph_runner_id=graph_runner_id,
            node_type=db.NodeType.COMPONENT,
            is_start_node=is_start_node,
        )
        session.add(node_to_graph_runner)

    await session.commit()


async def graph_runner_exists(session: AsyncSession, graph_id: UUID) -> bool:
    stmt = select(exists().where(db.GraphRunner.id == graph_id))
    result = await session.execute(stmt)
    return result.scalar()


async def get_component_nodes(session: AsyncSession, graph_runner_id: UUID) -> list[ComponentNodeDTO]:
    result = await session.execute(
        select(db.ComponentInstance, db.GraphRunnerNode)
        .join(db.GraphRunnerNode, db.ComponentInstance.id == db.GraphRunnerNode.node_id)
        .where(db.GraphRunnerNode.graph_runner_id == graph_runner_id)
    )
    rows = result.all()
    return [
        ComponentNodeDTO(
            id=component.id,
            name=component.name,
            is_start_node=node.is_start_node,
            component_instance_id=component.id,
            graph_runner_id=graph_runner_id,
        )
        for component, node in rows
    ]


async def get_graph_runner_nodes(session: AsyncSession, graph_runner_id: UUID) -> list[db.GraphRunner]:
    result = await session.execute(
        select(db.GraphRunner)
        .join(db.GraphRunnerNode, db.GraphRunner.id == db.GraphRunnerNode.node_id)
        .where(db.GraphRunnerNode.graph_runner_id == graph_runner_id)
    )
    return result.scalars().all()


async def get_start_components(session: AsyncSession, graph_runner_id: UUID) -> list[db.ComponentInstance]:
    result = await session.execute(
        select(db.ComponentInstance)
        .join(db.GraphRunnerNode, db.GraphRunnerNode.node_id == db.ComponentInstance.id)
        .where(
            db.GraphRunnerNode.graph_runner_id == graph_runner_id,
            db.GraphRunnerNode.is_start_node.is_(True),
        )
    )
    return result.scalars().all()


async def get_input_component(session: AsyncSession, graph_runner_id: UUID) -> Optional[db.ComponentInstance]:
    result = await session.execute(
        select(db.ComponentInstance)
        .join(db.GraphRunnerNode, db.GraphRunnerNode.node_id == db.ComponentInstance.id)
        .join(db.Component, db.Component.id == db.ComponentInstance.component_id)
        .where(
            db.GraphRunnerNode.graph_runner_id == graph_runner_id,
            db.Component.id == COMPONENT_UUIDS["input"],
            db.GraphRunnerNode.is_start_node.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def delete_node(session: AsyncSession, node_id: UUID):
    result = await session.execute(select(db.GraphRunnerNode).where(db.GraphRunnerNode.node_id == node_id))
    node = result.scalar_one_or_none()
    if node:
        LOGGER.info(f"Deleting node with id {node_id}")
        await session.delete(node)
        await session.commit()
    else:
        raise ValueError(f"Node with ID {node_id} does not exist in the graph runner.")


async def delete_graph_runner(session: AsyncSession, graph_id: UUID) -> None:
    LOGGER.info(f"Deleting graph runner with id {graph_id}")
    await session.execute(sql_delete(db.GraphRunner).where(db.GraphRunner.id == graph_id))
    await session.commit()


async def add_input_component_to_graph(session: AsyncSession, graph_runner_id: UUID) -> db.ComponentInstance:
    input_component = await create_input_component(session)
    await upsert_component_node(
        session=session,
        graph_runner_id=graph_runner_id,
        component_instance_id=input_component.id,
        is_start_node=True,
    )
    await session.commit()
    return input_component
