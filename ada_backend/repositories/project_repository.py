from typing import Optional
from uuid import UUID
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ada_backend.database import models as db
from ada_backend.schemas.project_schema import GraphRunnerEnvDTO, ProjectWithGraphRunnersSchema

LOGGER = logging.getLogger(__name__)


# --- READ operations ---
async def get_project(
    session: AsyncSession,
    project_id: Optional[UUID] = None,
    project_name: Optional[str] = None,
) -> Optional[db.Project]:
    if project_id is not None:
        result = await session.execute(
            select(db.Project).where(db.Project.id == project_id)
        )
        return result.scalar_one_or_none()
    if project_name is not None:
        result = await session.execute(
            select(db.Project).where(db.Project.name == project_name)
        )
        return result.scalar_one_or_none()
    raise ValueError("Either project_id or project_name must be provided")


async def get_project_with_details(
    session: AsyncSession,
    project_id: UUID,
) -> ProjectWithGraphRunnersSchema:
    result = await session.execute(
        select(db.Project, db.ProjectEnvironmentBinding)
        .join(db.ProjectEnvironmentBinding, db.ProjectEnvironmentBinding.project_id == db.Project.id)
        .where(db.Project.id == project_id)
    )
    results = result.all()

    graph_runners = [
        GraphRunnerEnvDTO(graph_runner_id=project_env_gr.graph_runner_id, env=project_env_gr.environment)
        for _, project_env_gr in results
    ]

    project = results[0][0] if results else None

    return ProjectWithGraphRunnersSchema(
        project_id=project.id if project else None,
        project_name=project.name if project else None,
        graph_runners=graph_runners,
        companion_image_url=project.companion_image_url if project else None,
        description=project.description if project else None,
        organization_id=project.organization_id if project else None,
        created_at=str(project.created_at) if project else None,
        updated_at=str(project.updated_at) if project else None,
    )


async def get_projects_by_organization_service(
    session: AsyncSession,
    organization_id: UUID,
) -> list[db.Project]:
    result = await session.execute(
        select(db.Project).where(db.Project.organization_id == organization_id)
    )
    return result.scalars().all()


# --- CREATE operations ---
async def insert_project(
    session: AsyncSession,
    project_id: UUID,
    project_name: str,
    organization_id: UUID,
    description: Optional[str] = None,
    companion_image_url: Optional[str] = None,
) -> db.Project:
    project = db.Project(
        id=project_id,
        name=project_name,
        description=description,
        organization_id=organization_id,
        companion_image_url=companion_image_url,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


# --- UPDATE operations ---
async def update_project(
    session: AsyncSession,
    project_id: UUID,
    project_name: Optional[str] = None,
    description: Optional[str] = None,
    companion_image_url: Optional[str] = None,
) -> db.Project:
    project = await get_project(session, project_id=project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found.")

    if project_name:
        project.name = project_name
    if description:
        project.description = description
    if companion_image_url:
        project.companion_image_url = companion_image_url

    await session.commit()
    await session.refresh(project)
    return project


# --- DELETE operations ---
async def delete_project(
    session: AsyncSession,
    project_id: UUID,
) -> None:
    project = await get_project(session, project_id=project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found.")

    LOGGER.info(f"Deleting project with id {project_id} and name {project.name}")
    await session.delete(project)
    await session.commit()
