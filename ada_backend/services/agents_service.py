import uuid
from uuid import UUID
import logging

from sqlalchemy.orm import Session

from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.repositories.agent_repository import add_ai_agent_component_to_graph, get_agents_by_organization
from ada_backend.repositories.env_repository import bind_graph_runner_to_project
from ada_backend.repositories.graph_runner_repository import insert_graph_runner
from ada_backend.repositories.parameters_repository import get_specific_basic_parameter
from ada_backend.repositories.project_repository import get_project, insert_project
from ada_backend.schemas.agent_schema import AgentUpdateSchema, ProjectAgentSchema, AgentInfoSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema, ComponentRelationshipSchema
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateResponse, GraphUpdateSchema
from ada_backend.schemas.project_schema import GraphRunnerEnvDTO, ProjectWithGraphRunnersSchema
from ada_backend.segment_analytics import track_agent_created
from ada_backend.services.errors import ProjectNotFound
from ada_backend.database import models as db
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_service


LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT_PARAMETER_DEF_ID = UUID("1cd1cd58-f066-4cf5-a0f5-9b2018fc4c6a")
SYSTEM_PROMPT_PARAMETER_NAME = "initial_prompt"


def get_all_agents_service(session: Session, organization_id: UUID) -> list[ProjectAgentSchema]:
    agents = get_agents_by_organization(session, organization_id)
    return [
        ProjectAgentSchema(
            id=agent.id,
            name=agent.name,
            description=agent.description,
        )
        for agent in agents
    ]


def get_agent_by_id_service(session: Session, agent_id: UUID, version_id: UUID) -> AgentInfoSchema:
    project = get_project(session, project_id=agent_id)
    if not project:
        return ProjectNotFound(agent_id)
    graph_response = get_graph_service(session, project_id=agent_id, graph_runner_id=version_id)
    model_parameters = []
    tools = []
    for component_instance in graph_response.component_instances:
        if component_instance.component_id == COMPONENT_UUIDS["base_ai_agent"]:
            for param in component_instance.parameters:
                if param.id == SYSTEM_PROMPT_PARAMETER_DEF_ID:
                    system_prompt = param.value if param.value else param.default
                elif param.id in [
                    UUID("89efb2e1-9228-44db-91d6-871a41042067"),
                    UUID("5bdece0d-bbc1-4cc7-a192-c4b7298dc163"),
                    UUID("f7dbbe12-e6ff-5bfe-b006-f6bf0e9cbf4d"),
                    UUID("3f8aa317-215a-4075-80ba-efca2a3d83ca"),
                    UUID("bf56e90a-5e2b-4777-9ef4-34838b8973b6"),
                    UUID("c22c1ce8-993f-4b6e-bccc-e70b8e87d04a"),
                    UUID("4ca78b43-4484-4a9d-bdab-e6dbdaff6da1"),
                    UUID("e2d157b4-f26d-41b4-9e47-62b5b041a9ff"),
                    UUID("e6caae01-d5ee-4afd-a995-e5ae9dbf3fbc"),
                ]:  # model parameters
                    model_parameters.append(param)
        else:  # consider all other components as tools
            tools.append(component_instance)

    return AgentInfoSchema(
        name=project.name,
        organization_id=project.organization_id,
        system_prompt=system_prompt,
        model_parameters=model_parameters,
        tools=tools,
    )


def create_new_agent_service(
    session: Session, user_id: UUID, organization_id: UUID, agent_data: ProjectAgentSchema
) -> ProjectWithGraphRunnersSchema:
    project = insert_project(
        session=session,
        project_id=agent_data.id,
        project_name=agent_data.name,
        description=agent_data.description,
        organization_id=organization_id,
        project_type=db.ProjectType.AGENT,
    )
    graph_runner = insert_graph_runner(
        session=session,
        graph_id=uuid.uuid4(),
        add_input=False,
    )
    graph_runner_id = graph_runner.id
    bind_graph_runner_to_project(
        session=session,
        graph_runner_id=graph_runner_id,
        project_id=project.id,
        env=db.EnvType.DRAFT,
    )
    add_ai_agent_component_to_graph(session, graph_runner_id)
    LOGGER.info(f"Created draft agent with version ID {graph_runner_id} for agent project {project.id}")
    track_agent_created(user_id, organization_id, project.id, project.name)
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
                env=db.EnvType.DRAFT,
            )
        ],
    )


def build_ai_agent_component(
    ai_agent_instance_id: UUID, model_config: list[db.BasicParameter], system_prompt: str
) -> ComponentInstanceSchema:
    """
    Helper function to build the AI agent component instance with the provided model configuration and system prompt.
    """
    parameters = model_config.copy()
    parameters.append(PipelineParameterSchema(value=system_prompt, name=SYSTEM_PROMPT_PARAMETER_NAME))
    return ComponentInstanceSchema(
        id=ai_agent_instance_id,
        component_id=COMPONENT_UUIDS["base_ai_agent"],
        name="AI Agent",
        parameters=parameters,
        is_start_node=True,
    )


async def update_agent_service(
    session: Session, user_id: UUID, agent_id: UUID, version_id: UUID, agent_data: AgentUpdateSchema
) -> GraphUpdateResponse:
    component_instances = agent_data.tools.copy()
    component_instances.append(
        build_ai_agent_component(
            ai_agent_instance_id=version_id,
            model_config=agent_data.model_parameters,
            system_prompt=agent_data.system_prompt,
        )
    )

    relationships: list[ComponentRelationshipSchema] = []
    for index, tool in enumerate(agent_data.tools):
        relationships.append(
            ComponentRelationshipSchema(
                parent_component_instance_id=version_id,
                child_component_instance_id=tool.id,
                parameter_name="agent_tools",
                order=index,
            )
        )
    graph_update_schema = GraphUpdateSchema(
        relationships=relationships, component_instances=component_instances, edges=[]
    )
    return await update_graph_service(
        session=session,
        graph_runner_id=version_id,
        project_id=agent_id,
        graph_project=graph_update_schema,
        user_id=user_id,
    )


def delete_agent_service(session, agent_id):
    # Implementation to delete an agent from the database
    pass
