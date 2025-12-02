from uuid import UUID
import uuid
from typing import Optional
import traceback

from sqlalchemy.orm import Session
import networkx as nx

from datetime import datetime

from ada_backend.database.models import EnvType, OrgSecretType, CallType
from ada_backend.services.tag_service import compose_tag_name
from ada_backend.repositories.edge_repository import get_edges
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.services.agent_builder_service import instantiate_component
from ada_backend.services.errors import ProjectNotFound, EnvironmentNotFound, OrganizationLimitExceededError
from ada_backend.repositories.credits_repository import get_organization_total_credits, get_organization_limit
from engine.graph_runner.graph_runner import GraphRunner
from engine.llm_services.utils import LLMKeyLimitExceededError
from ada_backend.repositories.graph_runner_repository import (
    get_component_nodes,
    get_graph_runner_for_env,
    get_start_components,
    graph_runner_exists,
    delete_temp_folder,
)
from ada_backend.repositories.port_mapping_repository import list_port_mappings_for_graph
from ada_backend.repositories.field_expression_repository import get_field_expressions_for_instances
from ada_backend.repositories.project_repository import get_project, get_project_with_details
from ada_backend.repositories.organization_repository import get_organization_secrets
from engine.graph_runner.runnable import Runnable
from engine.trace.trace_context import get_trace_manager
from engine.trace.span_context import set_tracing_span
from engine.trace.span_context import get_tracing_span
from engine.field_expressions.serializer import from_json as expression_from_json


def get_organization_llm_providers(session: Session, organization_id: UUID) -> list[str]:
    organization_secrets = get_organization_secrets(
        session,
        organization_id=organization_id,
    )
    organization_secrets = (
        [
            organization_secret.key.split("_")[0]
            for organization_secret in organization_secrets
            if organization_secret.secret_type == OrgSecretType.LLM_API_KEY
        ]
        if organization_secrets
        else []
    )
    # TODO: Remove when add from front side
    organization_secrets.append("custom_llm")

    return organization_secrets


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
    # Fetch port mappings for this graph
    pms = list_port_mappings_for_graph(session, graph_runner_id)
    port_mappings = [
        {
            "source_instance_id": str(pm.source_instance_id),
            "source_port_name": pm.source_port_definition.name,
            "target_instance_id": str(pm.target_instance_id),
            "target_port_name": pm.target_port_definition.name,
            "dispatch_strategy": pm.dispatch_strategy,
        }
        for pm in pms
    ]

    component_instance_ids = [node.id for node in component_nodes]
    field_expressions = get_field_expressions_for_instances(session, component_instance_ids)
    expressions = []
    for expression in field_expressions:
        expression_ast = None
        if expression.expression_json:
            expression_ast = expression_from_json(expression.expression_json)
        expressions.append(
            {
                "target_instance_id": str(expression.component_instance_id),
                "field_name": expression.field_name,
                "expression_ast": expression_ast,
            }
        )

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

    return GraphRunner(
        graph,
        runnables,
        start_nodes,
        trace_manager=trace_manager,
        port_mappings=port_mappings,
        expressions=expressions,
    )


async def get_agent_for_project(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
) -> GraphRunner:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ProjectNotFound(project_id)

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
    call_type: CallType,
) -> ChatResponse:
    graph_runner = get_graph_runner_for_env(session=session, project_id=project_id, env=env)
    if not graph_runner:
        raise EnvironmentNotFound(project_id, env.value)
    return await run_agent(
        session=session,
        project_id=project_id,
        graph_runner_id=graph_runner.id,
        input_data=input_data,
        environment=env,
        call_type=call_type,
        tag_name=compose_tag_name(graph_runner.tag_version, graph_runner.version_name),
    )


async def run_agent(
    session: Session,
    project_id: UUID,
    graph_runner_id: UUID,
    input_data: dict,
    environment: EnvType,
    call_type: CallType,
    tag_name: Optional[str] = None,
) -> ChatResponse:
    project_details = get_project_with_details(session, project_id=project_id)
    if not project_details:
        raise ProjectNotFound(project_id)

    today = datetime.now()
    organization_limit = get_organization_limit(
        session=session,
        organization_id=project_details.organization_id,
        year=today.year,
        month=today.month,
    )
    if organization_limit and organization_limit.limit is not None:
        current_usage = get_organization_total_credits(
            session,
            project_details.organization_id,
            today.year,
            today.month,
        )
        if current_usage >= organization_limit.limit:
            raise OrganizationLimitExceededError(
                project_details.organization_id, organization_limit.limit, current_usage
            )
    agent = await get_agent_for_project(
        session,
        project_id=project_id,
        graph_runner_id=graph_runner_id,
    )

    # TODO : Add again the monitoring for frequently asked questions after parallelization of agent run
    # db_service = SQLLocalService(engine_url="sqlite:///ada_backend/database/monitor.db", dialect="sqlite")
    # asyncio.create_task(monitor_questions(db_service, project_id, input_data))
    uuid_for_temp_folder = str(uuid.uuid4())

    # Generate conversation_id if not provided
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    set_tracing_span(
        project_id=str(project_id),
        organization_id=str(project_details.organization_id),
        organization_llm_providers=get_organization_llm_providers(session, project_details.organization_id),
        conversation_id=conversation_id,
        uuid_for_temp_folder=uuid_for_temp_folder,
        environment=environment,
        call_type=call_type,
        graph_runner_id=graph_runner_id,
        tag_name=tag_name,
    )
    try:
        agent_output = await agent.run(
            input_data,
            is_root_execution=True,
        )
        params = get_tracing_span()
    except LLMKeyLimitExceededError:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        raise ValueError(f"Error running agent: {tb}") from e
    finally:
        delete_temp_folder(uuid_for_temp_folder)
    return ChatResponse(
        message=agent_output.last_message.content,
        artifacts=agent_output.artifacts,
        error=agent_output.error,
        trace_id=params.trace_id,
    )
