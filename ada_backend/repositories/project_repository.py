from typing import Optional
from uuid import UUID
import logging

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, exists

from ada_backend.database import models as db
from ada_backend.schemas.project_schema import (
    GraphRunnerEnvDTO,
    ProjectWithGraphRunnersSchema,
)
from ada_backend.repositories.template_repository import TEMPLATE_ORGANIZATION_ID

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
) -> Optional[ProjectWithGraphRunnersSchema]:
    project = session.query(db.Project).filter(db.Project.id == project_id).first()

    if not project:
        return None

    graph_runner_rows = (
        session.query(db.GraphRunner, db.ProjectEnvironmentBinding)
        .outerjoin(
            db.ProjectEnvironmentBinding,
            (db.GraphRunner.id == db.ProjectEnvironmentBinding.graph_runner_id)
            & (db.ProjectEnvironmentBinding.project_id == project_id),
        )
        .filter(
            db.GraphRunner.id.in_(
                session.query(db.ProjectEnvironmentBinding.graph_runner_id).filter(
                    db.ProjectEnvironmentBinding.project_id == project_id
                )
            )
        )
        .order_by(db.GraphRunner.created_at, db.ProjectEnvironmentBinding.created_at, db.GraphRunner.id)
    ).all()

    graph_runners_with_env = [
        GraphRunnerEnvDTO(
            graph_runner_id=graph_runner.id,
            env=env_binding.environment if env_binding else None,
            tag_version=graph_runner.tag_version,
            version_name=graph_runner.version_name,
            change_log=graph_runner.change_log,
        )
        for graph_runner, env_binding in graph_runner_rows
    ]

    return ProjectWithGraphRunnersSchema(
        project_id=project.id,
        project_name=project.name,
        project_type=project.type,
        graph_runners=graph_runners_with_env,
        description=project.description,
        organization_id=project.organization_id,
        created_at=str(project.created_at),
        updated_at=str(project.updated_at),
    )


# TODO: legacy: remove this function
def get_workflows_by_organization(
    session: Session,
    organization_id: UUID,
) -> list[db.WorkflowProject]:
    return session.query(db.WorkflowProject).filter(db.WorkflowProject.organization_id == organization_id).all()


def get_projects_by_organization_with_details(
    session: Session,
    organization_id: UUID,
    type: Optional[db.ProjectType] = db.ProjectType.WORKFLOW,
    include_templates: bool = False,
) -> list[ProjectWithGraphRunnersSchema]:
    """
    Get projects (both workflow and agent) by organization with graph runners and templates.
    """

    query = session.query(db.Project).options(
        joinedload(db.Project.envs).joinedload(db.ProjectEnvironmentBinding.graph_runner)
    )

    if include_templates:
        # Include own projects + production templates from template org
        has_production = exists().where(
            and_(
                db.ProjectEnvironmentBinding.project_id == db.Project.id,
                db.ProjectEnvironmentBinding.environment == db.EnvType.PRODUCTION,
            )
        )
        query = query.filter(
            or_(
                db.Project.organization_id == organization_id,
                and_(db.Project.organization_id == TEMPLATE_ORGANIZATION_ID, has_production),
            )
        )
    else:
        query = query.filter(db.Project.organization_id == organization_id)

    if type:
        query = query.filter(db.Project.type == type)

    projects = query.order_by(db.Project.created_at).all()

    project_schemas = []
    for project in projects:
        # Context-aware: templates only when viewed from other orgs
        is_template = (
            str(organization_id) != TEMPLATE_ORGANIZATION_ID
            and str(project.organization_id) == TEMPLATE_ORGANIZATION_ID
        )

        # For templates, only include production graph runners
        graph_runners = [
            GraphRunnerEnvDTO(
                graph_runner_id=env_binding.graph_runner.id,
                env=env_binding.environment,
                tag_version=env_binding.graph_runner.tag_version,
                version_name=env_binding.graph_runner.version_name,
                change_log=env_binding.graph_runner.change_log,
            )
            for env_binding in project.envs
            if env_binding.graph_runner and (not is_template or env_binding.environment == db.EnvType.PRODUCTION)
        ]

        project_schemas.append(
            ProjectWithGraphRunnersSchema(
                project_id=project.id,
                project_name=project.name,
                description=project.description,
                organization_id=project.organization_id,
                project_type=project.type,
                created_at=str(project.created_at),
                updated_at=str(project.updated_at),
                graph_runners=graph_runners,
                is_template=is_template,
            )
        )

    return project_schemas


# --- CREATE operations ---
def insert_project(
    session: Session,
    project_id: UUID,
    project_name: str,
    organization_id: UUID,
    description: Optional[str] = None,
    project_type: Optional[db.ProjectType] = db.ProjectType.WORKFLOW,
) -> db.Project:
    if project_type == db.ProjectType.WORKFLOW:
        project = db.WorkflowProject(
            id=project_id,
            name=project_name,
            description=description,
            organization_id=organization_id,
            type=project_type,
        )
    elif project_type == db.ProjectType.AGENT:
        project = db.AgentProject(
            id=project_id,
            name=project_name,
            description=description,
            organization_id=organization_id,
            type=project_type,
        )
    else:
        raise ValueError(f"Invalid project_type: {project_type!r}")
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
) -> db.Project:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found.")
    if project_name:
        project.name = project_name
    if description:
        project.description = description
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