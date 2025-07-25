from typing import Optional
from uuid import UUID
import logging

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.schemas.project_schema import GraphRunnerEnvDTO, ProjectWithGraphRunnersSchema

LOGGER = logging.getLogger(__name__)


# --- READ operations ---
def get_project(
    session: Session,
    project_id: Optional[UUID] = None,
    project_name: Optional[str] = None,
) -> Optional[db.Project]:
    """
    Retrieves a specific project by ID or name.

    Args:
        session (Session): SQLAlchemy session.
        project_id (Optional[UUID]): ID of the project to retrieve.
        project_name (Optional[str]): Name of the project to retrieve.

    Returns:
        Optional[db.Project]: The Project object if found, otherwise None.
    """
    if project_id is not None:
        return session.query(db.Project).filter(db.Project.id == project_id).first()
    if project_name is not None:
        return session.query(db.Project).filter(db.Project.name == project_name).first()
    raise ValueError("Either project_id or project_name must be provided")


def get_project_with_details(
    session: Session,
    project_id: UUID,
) -> ProjectWithGraphRunnersSchema:
    results = (
        session.query(db.Project, db.ProjectEnvironmentBinding)
        .join(db.ProjectEnvironmentBinding, db.ProjectEnvironmentBinding.project_id == db.Project.id)
        .filter(db.Project.id == project_id)
    ).all()
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


def get_projects_by_organization_service(
    session: Session,
    organization_id: UUID,
) -> list[db.Project]:
    return session.query(db.Project).filter(db.Project.organization_id == organization_id).all()


# --- CREATE operations ---
def insert_project(
    session: Session,
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
    session.commit()
    session.refresh(project)
    return project


# --- UPDATE operations ---
def update_project(
    session: Session,
    project_id: UUID,
    project_name: Optional[str] = None,
    description: Optional[str] = None,
    companion_image_url: Optional[str] = None,
) -> db.Project:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found.")
    if project_name:
        project.name = project_name
    if description:
        project.description = description
    if companion_image_url:
        project.companion_image_url = companion_image_url
    session.commit()
    session.refresh(project)
    return project


# --- DELETE operations ---
def delete_project(
    session: Session,
    project_id: UUID,
) -> None:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found.")
    LOGGER.info(f"Deleting project with id {project_id} and name {project.name}")
    session.delete(project)
    session.commit()
