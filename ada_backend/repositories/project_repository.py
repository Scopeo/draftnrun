import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, distinct, exists, or_, select
from sqlalchemy.orm import Session, joinedload

from ada_backend.database import models as db
from ada_backend.repositories.template_repository import TEMPLATE_ORGANIZATION_ID
from ada_backend.schemas.project_schema import (
    GraphRunnerEnvDTO,
    ProjectWithGraphRunnersSchema,
)

LOGGER = logging.getLogger(__name__)


def _extract_tags(project: db.Project) -> list[str]:
    return sorted(pt.tag for pt in project.tags) if project.tags else []


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
    project = (
        session.query(db.Project)
        .options(
            joinedload(db.Project.envs)
            .joinedload(db.ProjectEnvironmentBinding.graph_runner)
            .load_only(
                db.GraphRunner.id,
                db.GraphRunner.tag_version,
                db.GraphRunner.version_name,
                db.GraphRunner.change_log,
                db.GraphRunner.created_at,
            ),
            joinedload(db.Project.tags),
        )
        .filter(db.Project.id == project_id)
        .first()
    )

    if not project:
        return None

    graph_runners_data = [
        (
            env_binding.graph_runner,
            env_binding,
            GraphRunnerEnvDTO(
                graph_runner_id=env_binding.graph_runner.id,
                env=env_binding.environment,
                tag_version=env_binding.graph_runner.tag_version,
                version_name=env_binding.graph_runner.version_name,
                change_log=env_binding.graph_runner.change_log,
            ),
        )
        for env_binding in project.envs
        if env_binding.graph_runner
    ]

    graph_runners_data.sort(
        key=lambda x: (x[0].created_at, x[1].created_at, x[0].id)
    )

    graph_runners_with_env = [dto for _, _, dto in graph_runners_data]

    return ProjectWithGraphRunnersSchema(
        project_id=project.id,
        project_name=project.name,
        project_type=project.type,
        graph_runners=graph_runners_with_env,
        description=project.description,
        icon=project.icon,
        icon_color=project.icon_color,
        organization_id=project.organization_id,
        created_at=str(project.created_at),
        updated_at=str(project.updated_at),
        tags=_extract_tags(project),
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
    tags: Optional[list[str]] = None,
) -> list[ProjectWithGraphRunnersSchema]:
    """
    Get projects (both workflow and agent) by organization with graph runners and templates.
    When tags is provided, only projects that have ALL specified tags are returned.
    """

    query = session.query(db.Project).options(
        joinedload(db.Project.envs)
        .joinedload(db.ProjectEnvironmentBinding.graph_runner)
        .load_only(
            db.GraphRunner.id,
            db.GraphRunner.tag_version,
            db.GraphRunner.version_name,
            db.GraphRunner.change_log,
        ),
        joinedload(db.Project.tags),
    )

    if include_templates:
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

    if tags:
        for tag in tags:
            normalized = tag.lower().strip()
            query = query.filter(
                exists().where(
                    and_(
                        db.ProjectTag.project_id == db.Project.id,
                        db.ProjectTag.tag == normalized,
                    )
                )
            )

    projects = query.order_by(db.Project.created_at).all()

    project_schemas = []
    for project in projects:
        is_template = (
            str(organization_id) != TEMPLATE_ORGANIZATION_ID
            and str(project.organization_id) == TEMPLATE_ORGANIZATION_ID
        )

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
                icon=project.icon,
                icon_color=project.icon_color,
                organization_id=project.organization_id,
                project_type=project.type,
                created_at=str(project.created_at),
                updated_at=str(project.updated_at),
                graph_runners=graph_runners,
                is_template=is_template,
                tags=_extract_tags(project),
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
    icon: Optional[str] = None,
    icon_color: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> db.Project:
    if project_type == db.ProjectType.WORKFLOW:
        project = db.WorkflowProject(
            id=project_id,
            name=project_name,
            description=description,
            organization_id=organization_id,
            type=project_type,
            icon=icon,
            icon_color=icon_color,
        )
    elif project_type == db.ProjectType.AGENT:
        project = db.AgentProject(
            id=project_id,
            name=project_name,
            description=description,
            organization_id=organization_id,
            type=project_type,
            icon=icon,
            icon_color=icon_color,
        )
    else:
        raise ValueError(f"Invalid project_type: {project_type!r}")
    session.add(project)
    if tags:
        for tag in tags:
            session.add(db.ProjectTag(project_id=project_id, tag=tag.lower().strip()))
    session.commit()
    session.refresh(project)
    return project


# --- UPDATE operations ---
def update_project(
    session: Session,
    project_id: UUID,
    project_name: Optional[str] = None,
    description: Optional[str] = None,
    icon: Optional[str] = None,
    icon_color: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> db.Project:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found.")
    if project_name:
        project.name = project_name
    if description:
        project.description = description
    if icon is not None:
        project.icon = icon
    if icon_color is not None:
        project.icon_color = icon_color
    if tags is not None:
        session.query(db.ProjectTag).filter(db.ProjectTag.project_id == project_id).delete()
        for tag in tags:
            session.add(db.ProjectTag(project_id=project_id, tag=tag.lower().strip()))
    session.commit()
    session.refresh(project)
    return project


# --- TAG operations ---
def add_tags_to_project(
    session: Session,
    project_id: UUID,
    tags: list[str],
) -> list[str]:
    existing = {
        row.tag
        for row in session.query(db.ProjectTag.tag).filter(db.ProjectTag.project_id == project_id).all()
    }
    for tag in tags:
        normalized = tag.lower().strip()
        if normalized and normalized not in existing:
            session.add(db.ProjectTag(project_id=project_id, tag=normalized))
            existing.add(normalized)
    session.commit()
    return sorted(existing)


def remove_tag_from_project(
    session: Session,
    project_id: UUID,
    tag: str,
) -> list[str]:
    session.query(db.ProjectTag).filter(
        db.ProjectTag.project_id == project_id,
        db.ProjectTag.tag == tag.lower().strip(),
    ).delete()
    session.commit()
    remaining = session.query(db.ProjectTag.tag).filter(db.ProjectTag.project_id == project_id).all()
    return sorted(row.tag for row in remaining)


def get_tags_for_organization(
    session: Session,
    organization_id: UUID,
) -> list[str]:
    rows = (
        session.execute(
            select(distinct(db.ProjectTag.tag))
            .join(db.Project, db.ProjectTag.project_id == db.Project.id)
            .where(db.Project.organization_id == organization_id)
            .order_by(db.ProjectTag.tag)
        )
        .scalars()
        .all()
    )
    return list(rows)


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
