from uuid import UUID, uuid4

from ada_backend.database.models import EnvType
from ada_backend.schemas.project_schema import ProjectCreateSchema
from ada_backend.services.project_service import create_workflow, get_project_service

ORGANIZATION_ID = UUID("37b7d67f-8f29-4fce-8085-19dea582f605")  # umbrella organization


def create_project_and_graph_runner(
    session,
    project_name_prefix: str = "test",
    description: str = "Test project",
) -> tuple[UUID, UUID]:
    project_id = uuid4()
    user_id = uuid4()
    project_payload = ProjectCreateSchema(
        project_id=project_id,
        project_name=f"{project_name_prefix}_{project_id}",
        description=description,
    )
    create_workflow(
        session=session,
        user_id=user_id,
        organization_id=ORGANIZATION_ID,
        project_schema=project_payload,
    )

    project_details = get_project_service(session, project_id)
    draft_graph_runner_id = next(gr.graph_runner_id for gr in project_details.graph_runners if gr.env == EnvType.DRAFT)
    return project_id, draft_graph_runner_id
