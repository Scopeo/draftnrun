from uuid import UUID
from logging import getLogger
import uuid

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
    get_projects_by_organization_service,
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
from ada_backend.segment_analytics import track_project_created, track_project_saved, track_user_get_project_list


LOGGER = getLogger(__name__)


def get_project_service(session: Session, project_id: UUID) -> ProjectWithGraphRunnersSchema:
    project_with_detail = get_project_with_details(session, project_id=project_id)
    return project_with_detail


def get_projects_by_organization(
    session: Session,
    organization_id: UUID,
    user_id: UUID = None,
) -> list[ProjectResponse]:
    if user_id:
        track_user_get_project_list(user_id, organization_id)
    projects = get_projects_by_organization_service(session, organization_id)
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


def delete_project_service(session: Session, project_id: UUID) -> ProjectDeleteResponse:
    graph_runners = get_graph_runners_by_project(session, project_id)
    for graph_runner in graph_runners:
        if graph_runner_exists(session, graph_runner.id):
            delete_graph_runner_service(session, graph_runner.id)
    delete_project(session, project_id)
    return ProjectDeleteResponse(
        project_id=project_id, graph_runner_ids=[graph_runner.id for graph_runner in graph_runners]
    )


def create_project(
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
        companion_image_url=project_schema.companion_image_url,
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
        companion_image_url=project.companion_image_url,
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
        companion_image_url=project_schema.companion_image_url,
    )
    track_project_saved(user_id, project_id)
    return ProjectSchema(
        project_id=project_id, project_name=project_schema.project_name, description=project_schema.description
    )
