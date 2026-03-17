import logging
import traceback
import uuid
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import networkx as nx
from sqlalchemy.orm import Session

from ada_backend.context import set_run_variables
from ada_backend.database.models import CallType, EnvType, OrgSecretType, ResponseFormat
from ada_backend.repositories.credits_repository import get_organization_limit, get_organization_total_credits
from ada_backend.repositories.edge_repository import get_edges
from ada_backend.repositories.graph_runner_repository import (
    delete_temp_folder,
    get_component_nodes,
    get_graph_runner_for_env,
    graph_runner_exists,
)
from ada_backend.repositories.input_port_instance_repository import get_input_port_instances_for_component_instance
from ada_backend.repositories.organization_repository import get_organization_secrets
from ada_backend.repositories.port_mapping_repository import get_source_port_name, list_port_mappings_for_graph
from ada_backend.repositories.project_repository import get_project, get_project_with_details
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.services.agent_builder_service import instantiate_component
from ada_backend.services.errors import (
    EnvironmentNotFound,
    GraphNotFound,
    OrganizationLimitExceededError,
    ProjectNotFound,
)
from ada_backend.services.file_response_service import (
    process_files_for_response,
    save_input_files_to_temp_folder,
    temp_folder_exists,
)
from ada_backend.services.graph_reachability import find_reachable_nodes
from ada_backend.services.tag_service import compose_tag_name
from ada_backend.services.variable_resolution_service import resolve_variables
from engine.components.errors import (
    CategorizationError,
    KeyTypePromptTemplateError,
    MissingKeyPromptTemplateError,
    NoMatchingRouteError,
)
from engine.field_expressions.serializer import from_json as expression_from_json
from engine.graph_runner.graph_runner import GraphRunner
from engine.graph_runner.runnable import Runnable
from engine.trace.span_context import get_tracing_span, set_tracing_span
from engine.trace.trace_context import get_trace_manager

LOGGER = logging.getLogger(__name__)


def _extract_set_ids(input_data: dict) -> list[str]:
    """Extract set_id/set_ids from input_data.

    Pops set_id/set_ids from input_data so they are not passed downstream.
    Returns a list of set IDs (may be empty).
    """
    set_id = input_data.pop("set_id", None)
    set_ids = input_data.pop("set_ids", None)
    return set_ids if set_ids else ([set_id] if set_id else [])


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


def setup_tracing_context(
    session: Session,
    project_id: UUID,
    **additional_tracing_params,
) -> tuple[UUID, list[str]]:
    project_details = get_project_with_details(session, project_id=project_id)
    if not project_details:
        raise ProjectNotFound(project_id)

    organization_llm_providers = get_organization_llm_providers(session, project_details.organization_id)

    set_tracing_span(
        project_id=str(project_id),
        organization_id=str(project_details.organization_id),
        organization_llm_providers=organization_llm_providers,
        **additional_tracing_params,
    )

    return project_details.organization_id, organization_llm_providers


async def build_graph_runner(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    variables: dict[str, Any] | None = None,
    event_callback=None,
) -> GraphRunner:
    trace_manager = get_trace_manager()
    # TODO: Add the get_graph_runner_nodes function when we will handle nested graphs
    component_nodes = get_component_nodes(session, graph_runner_id)
    edges = get_edges(session, graph_runner_id)

    trigger_node_ids = {str(node.id) for node in component_nodes if node.is_trigger}

    if trigger_node_ids:
        reachable_node_ids = find_reachable_nodes(component_nodes, edges, trigger_node_ids)
        all_node_ids = {str(node.id) for node in component_nodes}
        unreachable_node_ids = all_node_ids - reachable_node_ids

        if unreachable_node_ids:
            unreachable_names = [
                node.name for node in component_nodes if str(node.id) in unreachable_node_ids
            ]
            LOGGER.warning(
                "Skipping %d block(s) not triggered by a start block: %s",
                len(unreachable_node_ids),
                ", ".join(unreachable_names),
            )

        reachable_component_nodes = [node for node in component_nodes if str(node.id) in reachable_node_ids]
        reachable_edges = [
            edge for edge in edges
            if str(edge.source_node_id) in reachable_node_ids
            and str(edge.target_node_id) in reachable_node_ids
        ]
        start_nodes = [str(node_id) for node_id in trigger_node_ids]
    else:
        # TODO: Workaround for workflows that do not have a trigger — run all blocks.
        #  Once all workflows have a trigger, remove this fallback.
        LOGGER.info("No trigger node found in graph %s — running all blocks", graph_runner_id)
        reachable_node_ids = {str(node.id) for node in component_nodes}
        reachable_component_nodes = list(component_nodes)
        reachable_edges = list(edges)
        start_nodes = [str(node.id) for node in component_nodes if node.is_start_node]

    # Fetch port mappings for this graph
    port_mappings = list_port_mappings_for_graph(session, graph_runner_id)
    port_mappings_graph = []
    for port_mapping in port_mappings:
        source_port_name = get_source_port_name(port_mapping)
        if source_port_name is None:
            LOGGER.warning(
                f"PortMapping {port_mapping.id} has neither source_port_definition_id nor "
                "source_output_port_instance_id set; skipping"
            )
            continue
        port_mappings_graph.append({
            "source_instance_id": str(port_mapping.source_instance_id),
            "source_port_name": source_port_name,
            "target_instance_id": str(port_mapping.target_instance_id),
            "target_port_name": port_mapping.target_port_definition.name,
            "dispatch_strategy": port_mapping.dispatch_strategy,
        })

    component_instance_ids = [node.id for node in reachable_component_nodes]
    expressions: list[GraphRunner.ExpressionSpec] = []
    for component_instance_id in component_instance_ids:
        input_port_instances = get_input_port_instances_for_component_instance(
            session, component_instance_id, eager_load_field_expression=True
        )
        for input_port_instance in input_port_instances:
            if input_port_instance.field_expression and input_port_instance.field_expression.expression_json:
                expression_ast = expression_from_json(input_port_instance.field_expression.expression_json)
                expressions.append({
                    "target_instance_id": str(component_instance_id),
                    "field_name": input_port_instance.name,
                    "expression_ast": expression_ast,
                })

    runnables: dict[str, Runnable] = {}
    graph = nx.DiGraph()

    for component_node in reachable_component_nodes:
        agent = await instantiate_component(
            session=session,
            component_instance_id=component_node.id,
            project_id=project_id,
        )
        runnables[str(component_node.id)] = agent
        graph.add_node(str(component_node.id))

    for edge in reachable_edges:
        if edge.source_node_id:
            graph.add_edge(
                str(edge.source_node_id),
                str(edge.target_node_id),
                order=edge.order,
            )

    return GraphRunner(
        graph,
        runnables,
        start_nodes,
        trace_manager=trace_manager,
        port_mappings=port_mappings_graph,
        expressions=expressions,
        variables=variables,
        event_callback=event_callback,
    )


async def get_agent_for_project(
    session: Session,
    graph_runner_id: UUID,
    project_id: UUID,
    variables: dict[str, Any] | None = None,
    event_callback=None,
) -> GraphRunner:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ProjectNotFound(project_id)

    if graph_runner_exists(session, graph_id=graph_runner_id):
        return await build_graph_runner(
            session,
            graph_runner_id,
            project_id,
            variables=variables,
            event_callback=event_callback,
        )
    else:
        raise GraphNotFound(graph_runner_id)


async def run_env_agent(
    session: Session,
    project_id: UUID,
    env: EnvType,
    input_data: dict,
    call_type: CallType,
    response_format: Optional[ResponseFormat] = None,
    cron_id: Optional[UUID] = None,
    event_callback=None,
) -> ChatResponse:
    set_ids = _extract_set_ids(input_data)
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
        response_format=response_format,
        cron_id=cron_id,
        set_ids=set_ids,
        event_callback=event_callback,
    )


# TODO: agent_runner should not be aware of cron_id
async def run_agent(
    session: Session,
    project_id: UUID,
    graph_runner_id: UUID,
    input_data: dict,
    environment: EnvType,
    call_type: CallType,
    tag_name: Optional[str] = None,
    response_format: Optional[ResponseFormat] = None,
    cron_id: Optional[UUID] = None,
    set_ids: list[str] | None = None,
    event_callback=None,
) -> ChatResponse:
    if set_ids is None:
        set_ids = _extract_set_ids(input_data)

    project_details = get_project_with_details(session, project_id=project_id)
    if not project_details:
        raise ProjectNotFound(project_id)

    variables = resolve_variables(session, project_details.organization_id, set_ids, project_id=project_id)
    set_run_variables(variables)

    today = datetime.now()
    organization_limit = get_organization_limit(
        session=session,
        organization_id=project_details.organization_id,
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
    # TODO : Add again the monitoring for frequently asked questions after parallelization of agent run
    # db_service = SQLLocalService(engine_url="sqlite:///ada_backend/database/monitor.db", dialect="sqlite")
    # asyncio.create_task(monitor_questions(db_service, project_id, input_data))
    uuid_for_temp_folder = str(uuid.uuid4())

    # Generate conversation_id if not provided
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    save_input_files_to_temp_folder(input_data, uuid_for_temp_folder)

    tracing_params = {}
    if cron_id:
        tracing_params["cron_id"] = str(cron_id)

    setup_tracing_context(
        session=session,
        project_id=project_id,
        conversation_id=conversation_id,
        uuid_for_temp_folder=uuid_for_temp_folder,
        environment=environment,
        call_type=call_type,
        graph_runner_id=graph_runner_id,
        tag_name=tag_name,
        **tracing_params,
    )

    agent = await get_agent_for_project(
        session,
        project_id=project_id,
        graph_runner_id=graph_runner_id,
        variables=variables,
        event_callback=event_callback,
    )

    try:
        agent_output = await agent.run(
            input_data,
            is_root_execution=True,
        )
        params = get_tracing_span()
    except (MissingKeyPromptTemplateError, KeyTypePromptTemplateError, NoMatchingRouteError, CategorizationError):
        raise
    except Exception as e:
        tb = traceback.format_exc()
        raise ValueError(f"Error running agent: {tb}") from e
    finally:
        try:
            await agent.close()
        except Exception as e:
            LOGGER.error(f"Error closing agent resources: {e}", exc_info=True)
        # TODO: Manage other components cleanup on their own close() methods
        params = get_tracing_span()
        if params and params.shared_sandbox:
            try:
                await params.shared_sandbox.kill()
                LOGGER.info("Successfully cleaned up shared sandbox")
            except Exception as e:
                LOGGER.error(f"CRITICAL: Failed to cleanup shared sandbox (will leak resources): {e}")
            params.shared_sandbox = None

        files = []
        if response_format is not None and temp_folder_exists(uuid_for_temp_folder):
            try:
                files = process_files_for_response(
                    temp_folder_path=uuid_for_temp_folder,
                    org_id=str(project_details.organization_id),
                    project_id=str(project_id),
                    conversation_id=conversation_id,
                    response_format=response_format,
                )
            except Exception as e:
                LOGGER.error(
                    f"Error processing files for response: {str(e)}",
                    exc_info=True,
                )
        delete_temp_folder(uuid_for_temp_folder)
    return ChatResponse(
        message=agent_output.last_message.content,
        artifacts=agent_output.artifacts,
        error=agent_output.error,
        trace_id=params.trace_id,
        files=files,
    )
