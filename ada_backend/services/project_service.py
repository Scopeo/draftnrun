from uuid import UUID
from logging import getLogger
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import EnvType
from ada_backend.repositories.env_repository import bind_graph_runner_to_project
from ada_backend.repositories.graph_runner_repository import (
    get_graph_runners_by_project,
    graph_runner_exists,
    insert_graph_runner,
)
from ada_backend.services.graph.deploy_graph_service import clone_graph_runner
from ada_backend.repositories.project_repository import (
    get_project_with_details,
    get_workflows_by_organization,
    get_projects_by_organization_with_details,
    delete_project,
    insert_project,
    update_project,
)
from ada_backend.schemas.project_schema import (
    GraphRunnerEnvDTO,
    ProjectDeleteResponse,
    ProjectResponse,
    ProjectSchema,
    ProjectUpdateSchema,
    ProjectWithGraphRunnersSchema,
    ProjectCreateSchema,
)
from ada_backend.services.graph.delete_graph_service import delete_graph_runner_service
from ada_backend.services.errors import ProjectNotFound
from ada_backend.services.tag_service import compose_tag_name
from ada_backend.segment_analytics import track_project_created, track_project_saved, track_user_get_project_list

LOGGER = getLogger(__name__)


def get_project_service(session: Session, project_id: UUID) -> ProjectWithGraphRunnersSchema:
    project_with_detail = get_project_with_details(session, project_id=project_id)
    if not project_with_detail:
        raise ProjectNotFound(project_id)

    # Compose tag_name for each graph runner using the service layer
    for graph_runner in project_with_detail.graph_runners:
        graph_runner.tag_name = compose_tag_name(graph_runner.tag_version, graph_runner.version_name)

    return project_with_detail


# TODO: move to workflow_service
def get_workflows_by_organization_service(
    session: Session,
    organization_id: UUID,
    user_id: UUID = None,
) -> list[ProjectResponse]:
    if user_id:
        track_user_get_project_list(user_id, organization_id)
    projects = get_workflows_by_organization(session, organization_id)

    return [
        ProjectResponse(
            project_id=project.id,
            project_name=project.name,
            description=project.description,
            organization_id=project.organization_id,
            created_at=str(project.created_at),
            updated_at=str(project.updated_at),
        )
        for project in projects
    ]


def get_projects_by_organization_with_details_service(
    session: Session,
    organization_id: UUID,
    user_id: UUID = None,
    type: Optional[str] = None,
    include_templates: Optional[bool] = True,
) -> list[ProjectWithGraphRunnersSchema]:
    if user_id:
        track_user_get_project_list(user_id, organization_id)
    return get_projects_by_organization_with_details(session, organization_id, type, include_templates)


def delete_project_service(session: Session, project_id: UUID) -> ProjectDeleteResponse:
    graph_runners = get_graph_runners_by_project(session, project_id)
    for graph_runner in graph_runners:
        if graph_runner_exists(session, graph_runner.id):
            delete_graph_runner_service(session, graph_runner.id)
    delete_project(session, project_id)
    return ProjectDeleteResponse(
        project_id=project_id, graph_runner_ids=[graph_runner.id for graph_runner in graph_runners]
    )


# TODO: move to workflow_service
def create_workflow(
    session: Session,
    user_id: UUID,
    organization_id: UUID,
    project_schema: ProjectCreateSchema,
) -> ProjectWithGraphRunnersSchema:
    graph_runner_id = None
    if project_schema.template is not None:
        LOGGER.info(
            f"Creating project from template {project_schema.template.template_project_id}"
            f"with graph runner {project_schema.template.template_graph_runner_id}"
        )
        graph_runner_id = clone_graph_runner(
            session,
            project_schema.template.template_graph_runner_id,
            project_schema.template.template_project_id,
        )
    else:
        LOGGER.info("Creating a new graph runner for the project")
        graph_runner = insert_graph_runner(
            session=session,
            graph_id=uuid.uuid4(),
            add_input=True,
        )
        graph_runner_id = graph_runner.id
    project = insert_project(
        session=session,
        project_id=project_schema.project_id,
        organization_id=organization_id,
        project_name=project_schema.project_name,
        description=project_schema.description,
    )

    bind_graph_runner_to_project(
        session=session,
        graph_runner_id=graph_runner_id,
        project_id=project.id,
        env=EnvType.DRAFT,
    )
    LOGGER.info(f"Created draft graph runner with ID {graph_runner_id} for project {project.id}")

    track_project_created(user_id, organization_id, project.id, project.name)
    return ProjectWithGraphRunnersSchema(
        project_id=project.id,
        project_name=project.name,
        description=project.description,
        organization_id=organization_id,
        project_type=project.type,
        created_at=str(project.created_at),
        updated_at=str(project.updated_at),
        graph_runners=[
            GraphRunnerEnvDTO(
                graph_runner_id=graph_runner_id,
                env=EnvType.DRAFT,
            )
        ],
    )


def update_project_service(
    session: Session,
    user_id: UUID,
    project_id: UUID,
    project_schema: ProjectUpdateSchema,
) -> ProjectSchema:
    update_project(
        session=session,
        project_id=project_id,
        project_name=project_schema.project_name,
        description=project_schema.description,
    )
    track_project_saved(user_id, project_id)
    return ProjectSchema(
        project_id=project_id, project_name=project_schema.project_name, description=project_schema.description
    )
