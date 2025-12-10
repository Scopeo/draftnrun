from collections import defaultdict
from typing import DefaultDict
from uuid import UUID, uuid4
import logging

from sqlalchemy.orm import Session

from ada_backend.database.seed.seed_ai_agent import (
    AGENT_TOOLS_PARAMETER_NAME,
    AI_MODEL_PARAMETER_IDS,
    SYSTEM_PROMPT_PARAMETER_DEF_ID,
    SYSTEM_PROMPT_PARAMETER_NAME,
)
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.repositories.agent_repository import fetch_agents_with_graph_runners_by_organization
from ada_backend.repositories.graph_runner_repository import upsert_component_node
from ada_backend.repositories.project_repository import get_project
from ada_backend.repositories.utils import create_component_instance
from ada_backend.schemas.agent_schema import (
    AgentUpdateSchema,
    AgentWithGraphRunnersSchema,
    ProjectAgentSchema,
    AgentInfoSchema,
)
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema, ComponentRelationshipSchema
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateResponse, GraphUpdateSchema
from ada_backend.schemas.project_schema import GraphRunnerEnvDTO, ProjectWithGraphRunnersSchema
from ada_backend.segment_analytics import track_agent_created
from ada_backend.services.errors import ProjectNotFound, InvalidAgentTemplate
from ada_backend.database import models as db
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_with_history_service
from ada_backend.services.project_service import create_project_with_graph_runner
from ada_backend.services.tag_service import compose_tag_name
from ada_backend.services.pipeline.update_pipeline_service import create_or_update_component_instance


LOGGER = logging.getLogger(__name__)


def get_all_agents_service(session: Session, organization_id: UUID) -> list[AgentWithGraphRunnersSchema]:
    agents_with_graph_runners_rows = fetch_agents_with_graph_runners_by_organization(session, organization_id)
    agents_grouped_by_id: DefaultDict[UUID, dict] = defaultdict(lambda: {"agent": None, "graph_runners": []})
    for agent, graph_runner, project_env_binding in agents_with_graph_runners_rows:
        agent_group = agents_grouped_by_id[agent.id]
        agent_group["agent"] = agent
        agent_group["graph_runners"].append(
            GraphRunnerEnvDTO(
                graph_runner_id=graph_runner.id,
                env=project_env_binding.environment if project_env_binding else None,
                tag_version=graph_runner.tag_version,
                version_name=graph_runner.version_name,
                tag_name=compose_tag_name(graph_runner.tag_version, graph_runner.version_name),
                change_log=graph_runner.change_log,
            )
        )

    return [
        AgentWithGraphRunnersSchema(
            id=agent_data["agent"].id,
            name=agent_data["agent"].name,
            description=agent_data["agent"].description,
            graph_runners=agent_data["graph_runners"],
        )
        for agent_data in agents_grouped_by_id.values()
    ]


def _extract_system_prompt_and_model_params(
    component_instance: ComponentInstanceSchema,
) -> tuple[str, list[PipelineParameterSchema]]:
    """
    Extract system prompt and model parameters from an AI agent component instance.

    Args:
        component_instance: The AI agent component instance

    Returns:
        Tuple of (system_prompt, model_parameters)
    """
    system_prompt = ""
    model_parameters = []

    for param in component_instance.parameters:
        if param.id == SYSTEM_PROMPT_PARAMETER_DEF_ID:
            system_prompt = param.value if param.value else param.default
        elif param.id in AI_MODEL_PARAMETER_IDS.values():
            model_parameters.append(param)

    return system_prompt, model_parameters


def get_agent_by_id_service(session: Session, agent_id: UUID, graph_runner_id: UUID) -> AgentInfoSchema:
    agent_project = get_project(session, project_id=agent_id)
    if not agent_project:
        return ProjectNotFound(agent_id)

    graph_data = get_graph_service(session, project_id=agent_id, graph_runner_id=graph_runner_id)

    system_prompt = ""
    model_parameters: list[PipelineParameterSchema] = []
    agent_tools: list[ComponentInstanceSchema] = []

    for component_instance in graph_data.component_instances:
        is_ai_agent_component = (
            component_instance.is_start_node
            and component_instance.component_version_id == COMPONENT_VERSION_UUIDS["base_ai_agent"]
        )

        if is_ai_agent_component:
            system_prompt, model_parameters = _extract_system_prompt_and_model_params(component_instance)
        else:
            agent_tools.append(component_instance)

    return AgentInfoSchema(
        name=agent_project.name,
        description=agent_project.description,
        organization_id=agent_project.organization_id,
        system_prompt=system_prompt,
        model_parameters=model_parameters,
        tools=agent_tools,
    )


def _template_has_ai_agent(session: Session, template_project_id: UUID, template_graph_runner_id: UUID) -> bool:
    template_graph_data = get_graph_service(
        session, project_id=template_project_id, graph_runner_id=template_graph_runner_id
    )
    return any(
        component_instance.is_start_node
        and component_instance.component_version_id == COMPONENT_VERSION_UUIDS["base_ai_agent"]
        for component_instance in template_graph_data.component_instances
    )


def add_ai_agent_component_to_graph(session: Session, graph_runner_id: UUID) -> db.ComponentInstance:
    """
    Adds an AI agent component as a start node to the graph runner.

    Args:
        session (Session): SQLAlchemy session
        graph_runner_id (UUID): ID of the graph runner

    Returns:
        ComponentInstance: The created AI agent component instance
    """
    ai_agent_component = create_component_instance(
        session,
        component_version_id=COMPONENT_VERSION_UUIDS["base_ai_agent"],
        name="AI Agent",
        component_instance_id=graph_runner_id,
    )

    upsert_component_node(
        session=session,
        graph_runner_id=graph_runner_id,
        component_instance_id=ai_agent_component.id,
        is_start_node=True,
    )
    return ai_agent_component


def create_new_agent_service(
    session: Session, user_id: UUID, organization_id: UUID, agent_data: ProjectAgentSchema
) -> ProjectWithGraphRunnersSchema:
    project, graph_runner_id = create_project_with_graph_runner(
        session=session,
        organization_id=organization_id,
        project_id=agent_data.id,
        project_name=agent_data.name,
        description=agent_data.description,
        project_type=db.ProjectType.AGENT,
        template=agent_data.template,
        graph_id=agent_data.id,
        add_input=False,
    )

    if agent_data.template is None:
        add_ai_agent_component_to_graph(session, graph_runner_id)
    else:
        if not _template_has_ai_agent(
            session, agent_data.template.template_project_id, agent_data.template.template_graph_runner_id
        ):
            raise InvalidAgentTemplate(
                agent_data.template.template_project_id, agent_data.template.template_graph_runner_id
            )

    track_agent_created(user_id, organization_id, project.id, project.name)
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
                env=db.EnvType.DRAFT,
            )
        ],
    )


def build_ai_agent_component(
    ai_agent_instance_id: UUID, model_parameters: list[db.BasicParameter], system_prompt: str
) -> ComponentInstanceSchema:
    """
    Helper function to build the AI agent component instance with the provided model configuration and system prompt.
    """
    parameters = model_parameters.copy()
    parameters.append(PipelineParameterSchema(value=system_prompt, name=SYSTEM_PROMPT_PARAMETER_NAME))
    return ComponentInstanceSchema(
        id=ai_agent_instance_id,
        component_id=COMPONENT_UUIDS["base_ai_agent"],
        component_version_id=COMPONENT_VERSION_UUIDS["base_ai_agent"],
        name="AI Agent",
        parameters=parameters,
        is_start_node=True,
    )


def _build_tool_relationships(
    graph_runner_id: UUID, tools: list[ComponentInstanceSchema]
) -> list[ComponentRelationshipSchema]:
    """
    Build relationships linking tools to the AI agent.

    Args:
        graph_runner_id: ID of the graph runner (AI agent instance)
        tools: List of tool component instances

    Returns:
        List of component relationships
    """
    return [
        ComponentRelationshipSchema(
            parent_component_instance_id=graph_runner_id,
            child_component_instance_id=tool.id,
            parameter_name=AGENT_TOOLS_PARAMETER_NAME,
            order=index,
        )
        for index, tool in enumerate(tools)
    ]


async def update_agent_service(
    session: Session, user_id: UUID, agent_id: UUID, graph_runner_id: UUID, agent_data: AgentUpdateSchema
) -> GraphUpdateResponse:
    ai_agent_component = build_ai_agent_component(
        ai_agent_instance_id=graph_runner_id,
        model_parameters=agent_data.model_parameters,
        system_prompt=agent_data.system_prompt,
    )

    tools_with_ids = []
    for tool in agent_data.tools:
        if tool.id is None:
            tool.id = uuid4()
            LOGGER.info(f"Generated new instance ID {tool.id} for tool {tool.component_id}")
        else:
            LOGGER.info(f"Reusing existing instance ID {tool.id} for tool {tool.component_id}")

        create_or_update_component_instance(session, tool, agent_id)
        tools_with_ids.append(tool)

    all_component_instances = tools_with_ids.copy()
    all_component_instances.append(ai_agent_component)

    tool_relationships = _build_tool_relationships(graph_runner_id, tools_with_ids)

    graph_update_request = GraphUpdateSchema(
        relationships=tool_relationships, component_instances=all_component_instances, edges=[]
    )

    return await update_graph_with_history_service(
        session=session,
        graph_runner_id=graph_runner_id,
        project_id=agent_id,
        graph_project=graph_update_request,
        user_id=user_id,
    )
