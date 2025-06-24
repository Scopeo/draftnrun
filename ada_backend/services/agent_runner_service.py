from uuid import UUID

from sqlalchemy.orm import Session
import networkx as nx

from ada_backend.database.models import EnvType, OrgSecretType
from ada_backend.repositories.edge_repository import get_edges
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.services.agent_builder_service import get_default_values_for_sandbox, instantiate_component
from engine.graph_runner.graph_runner import GraphRunner
from ada_backend.repositories.graph_runner_repository import (
    get_component_nodes,
    get_graph_runner_for_env,
    get_input_component,
    get_start_components,
    graph_runner_exists,
)
from engine.agent.agent import Agent
from ada_backend.repositories.project_repository import get_project, get_project_with_details
from ada_backend.repositories.organization_repository import get_organization_secrets
from ada_backend.services.trace_service import get_token_usage
from engine.graph_runner.runnable import Runnable
from engine.trace.trace_context import get_trace_manager
from engine.trace.span_context import set_tracing_span

TOKEN_LIMIT = 2000000


async def build_graph_runner(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
) -> GraphRunner:
    trace_manager = get_trace_manager()
    # TODO: Add the get_graph_runner_nodes function when we will handle nested graphs
    component_nodes = get_component_nodes(session, graph_runner_id)
    edges = get_edges(session, graph_runner_id)
    start_nodes = [str(node.id) for node in get_start_components(session, graph_runner_id)]

    runnables: dict[str, Runnable] = {}
    graph = nx.DiGraph()

    for component_node in component_nodes:
        agent = instantiate_component(
            session=session,
            component_instance_id=component_node.id,
            project_id=project_id,
        )
        runnables[str(component_node.id)] = agent
        graph.add_node(str(component_node.id))

    for edge in edges:
        if edge.source_node_id:
            graph.add_edge(str(edge.source_node_id), str(edge.target_node_id), order=edge.order)

    return GraphRunner(graph, runnables, start_nodes, trace_manager=trace_manager)


async def get_agent_for_project(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
) -> Agent | GraphRunner:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found.")

    if graph_runner_exists(session, graph_id=graph_runner_id):
        return await build_graph_runner(
            session,
            graph_runner_id,
            project_id,
        )
    else:
        raise ValueError("Graph runner does not exist")


async def run_env_agent(
    session: Session,
    project_id: UUID,
    env: EnvType,
    input_data: dict,
) -> ChatResponse:
    graph_runner = get_graph_runner_for_env(session=session, project_id=project_id, env=env)
    if not graph_runner:
        raise ValueError(f"{env} graph runner not found for project {project_id}.")
    return await run_agent(
        session=session, project_id=project_id, graph_runner_id=graph_runner.id, input_data=input_data
    )


async def run_agent(
    session: Session,
    project_id: UUID,
    graph_runner_id: UUID,
    input_data: dict,
) -> ChatResponse:
    agent = await get_agent_for_project(
        session,
        project_id=project_id,
        graph_runner_id=graph_runner_id,
    )
    project_details = get_project_with_details(session, project_id=project_id)
    trace_manager_project_id = str(project_id)
    trace_manager_organization_id = str(project_details.organization_id)
    organization_secrets = get_organization_secrets(
        session,
        organization_id=project_details.organization_id,
    )
    trace_manager_organization_llm_providers = (
        [
            organization_secret.key.split("_")[0]
            for organization_secret in organization_secrets
            if organization_secret.secret_type == OrgSecretType.LLM_API_KEY
        ]
        if organization_secrets
        else []
    )
    set_tracing_span(
        project_id=trace_manager_project_id,
        organization_id=trace_manager_organization_id,
        organization_llm_providers=trace_manager_organization_llm_providers,
    )
    token_usage = get_token_usage(organization_id=project_details.organization_id)
    # TODO: Fix when token limit is reached and user try to use their own key
    if token_usage.total_tokens > TOKEN_LIMIT:
        raise ValueError(
            "You are currently using Draft'n run's default LLM key, which has exceeded its token limit. "
            "Please provide your own key."
        )

    # TODO : Add again the monitoring for frequently asked questions after parallelization of agent run
    # db_service = SQLLocalService(engine_url="sqlite:///ada_backend/database/monitor.db", dialect="sqlite")
    # asyncio.create_task(monitor_questions(db_service, project_id, input_data))
    input_component = get_input_component(session, graph_runner_id=graph_runner_id)
    if input_component:
        input_data = get_default_values_for_sandbox(session, input_component.id, project_id, input_data)
    try:
        agent_output = await agent.run(
            input_data,
        )
    except Exception as e:
        raise ValueError(f"Error running agent: {str(e)}") from e
    return ChatResponse(
        message=agent_output.last_message.content, artifacts=agent_output.artifacts, error=agent_output.error
    )
