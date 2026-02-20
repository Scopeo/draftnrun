from uuid import UUID, uuid4

from ada_backend.database.models import EnvType
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.pipeline.graph_schema import EdgeSchema, GraphUpdateSchema
from ada_backend.schemas.project_schema import ProjectCreateSchema
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.services.project_service import create_workflow, get_project_service

ORGANIZATION_ID = UUID("37b7d67f-8f29-4fce-8085-19dea582f605")  # umbrella organization

GRAPH_TEST_PROJECT_ID = UUID(
    "f7ddbfcb-6843-4ae9-a15b-40aa565b955b"
)  # graph test project (seeded in seed_project_db.py)


def create_project_and_graph_runner(
    session,
    organization_id: UUID = ORGANIZATION_ID,
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


async def create_graph_with_start_node_and_ai_agent(
    session, project_id: UUID, graph_runner_id: UUID, provider: str, model_name: str
):
    start_id = str(uuid4())
    ai_agent_id = str(uuid4())
    edge_id = uuid4()
    graph_payload = GraphUpdateSchema(
        component_instances=[
            ComponentInstanceSchema(
                id=start_id,
                component_id=COMPONENT_UUIDS["start"],
                component_version_id=COMPONENT_VERSION_UUIDS["start_v2"],
                name="Start",
                parameters=[
                    PipelineParameterSchema(
                        name="payload_schema",
                        value='{"messages": [{"role": "user", "content": "{{input}}"}]}',
                    )
                ],
                is_start_node=True,
            ),
            ComponentInstanceSchema(
                id=ai_agent_id,
                component_id=COMPONENT_UUIDS["base_ai_agent"],
                component_version_id=COMPONENT_VERSION_UUIDS["base_ai_agent"],
                name="AI Agent",
                parameters=[
                    PipelineParameterSchema(name="completion_model", value=f"{provider}:{model_name}"),
                ],
                is_start_node=False,
            ),
        ],
        relationships=[],
        edges=[
            EdgeSchema(
                id=edge_id,
                origin=UUID(start_id),
                destination=UUID(ai_agent_id),
                order=0,
            )
        ],
        port_mappings=[],
    )
    await update_graph_service(session, graph_runner_id, project_id, graph_payload)
    return ai_agent_id
