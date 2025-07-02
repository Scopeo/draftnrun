from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ada_backend.database.models import EnvType
from ada_backend.database import models as db


async def get_env_relationship_by_graph_runner_id(
    session: AsyncSession, graph_runner_id: UUID
) -> db.ProjectEnvironmentBinding:
    result = await session.execute(
        select(db.ProjectEnvironmentBinding).where(db.ProjectEnvironmentBinding.graph_runner_id == graph_runner_id)
    )
    env_relationship = result.scalar_one_or_none()
    if not env_relationship:
        raise ValueError(f"Graph runner with ID {graph_runner_id} not found.")
    return env_relationship


async def update_graph_runner_env(session: AsyncSession, graph_runner_id: UUID, env: EnvType) -> None:
    result = await session.execute(
        select(db.ProjectEnvironmentBinding).where(db.ProjectEnvironmentBinding.graph_runner_id == graph_runner_id)
    )
    env_relationship = result.scalar_one_or_none()
    if not env_relationship:
        raise ValueError(f"Graph runner with ID {graph_runner_id} not found.")
    env_relationship.environment = env
    session.add(env_relationship)
    await session.commit()


async def bind_graph_runner_to_project(
    session: AsyncSession,
    graph_runner_id: UUID,
    project_id: UUID,
    env: EnvType,
) -> db.ProjectEnvironmentBinding:
    relationship = db.ProjectEnvironmentBinding(
        graph_runner_id=graph_runner_id, project_id=project_id, environment=env
    )
    session.add(relationship)
    await session.commit()
    return relationship
