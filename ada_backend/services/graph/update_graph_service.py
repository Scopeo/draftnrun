import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ada_backend.database.models import EnvType
from ada_backend.repositories.component_repository import (
    get_component_instance_by_id,
    get_component_parameter_definition_by_component_id,
    upsert_sub_component_input,
)
from ada_backend.repositories.edge_repository import upsert_edge
from ada_backend.repositories.graph_runner_repository import (
    delete_node,
    get_component_nodes,
    graph_runner_exists,
    insert_graph_runner_and_bind_to_project,
    upsert_component_node,
)
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateResponse, GraphUpdateSchema
from ada_backend.services.agent_runner_service import get_agent_for_project
from ada_backend.services.graph.delete_graph_service import delete_component_instances_from_nodes
from ada_backend.services.pipeline.update_pipeline_service import create_or_update_component_instance

LOGGER = logging.getLogger(__name__)


async def update_graph_service(
    session: AsyncSession,
    graph_runner_id: UUID,
    project_id: UUID,
    graph_project: GraphUpdateSchema,
    env: Optional[EnvType] = None,
) -> GraphUpdateResponse:
    """
    Asynchronously creates or updates a complete graph runner including all component instances,
    their parameters, and relationships.
    """
    print("IS GRAPH EXISTING")
    if not await graph_runner_exists(session, graph_runner_id):
        LOGGER.info("Creating new graph")
        env = env if env else EnvType.DRAFT
        await insert_graph_runner_and_bind_to_project(session, graph_runner_id, project_id=project_id, env=env)
    # TODO: Add the get_graph_runner_nodes function when we will handle nested graphs
    previous_graph_nodes = set(node.id for node in await get_component_nodes(session, graph_runner_id))

    # Create/update all component instances
    print("Creating or updating component instances")
    instance_ids = set()
    for instance in graph_project.component_instances:
        instance_id = await create_or_update_component_instance(
            session=session, instance_data=instance, project_id=project_id
        )
        await upsert_component_node(
            session,
            graph_runner_id=graph_runner_id,
            component_instance_id=instance.id,
            is_start_node=instance.is_start_node,
        )
        instance_ids.add(instance_id)
    # Create relationships
    for relation in graph_project.relationships:
        # Validate that both components exist
        if not (
            relation.parent_component_instance_id in instance_ids
            and relation.child_component_instance_id in instance_ids
        ):
            raise ValueError("Invalid relationship: component instance not found")

        # Get parameter definition ID from name
        parent = await get_component_instance_by_id(session, relation.parent_component_instance_id)  # Await
        if not parent:
            raise ValueError("Invalid relationship: parent component instance not found")
        # TODO: Refactor to repository function that takes name and component_id or with dictionary for faster lookup
        param_defs = await get_component_parameter_definition_by_component_id(session, parent.component_id)
        param_def = next((p for p in param_defs if p.name == relation.parameter_name), None)
        if not param_def:
            raise ValueError(
                f"Parameter '{relation.parameter_name}' not found in "
                f"component definitions for component '{parent.component.name}'"
            )

        # Create relationship
        await upsert_sub_component_input(
            session=session,
            parent_component_instance_id=relation.parent_component_instance_id,
            child_component_instance_id=relation.child_component_instance_id,
            parameter_definition_id=param_def.id,
            order=relation.order,
        )
    for edge in graph_project.edges:
        if await graph_runner_exists(session, edge.destination) or await graph_runner_exists(
            session, edge.origin
        ):  # Await
            raise ValueError("Nested graphs are not supported")

        await upsert_edge(
            session,
            id=edge.id,
            source_node_id=edge.origin,
            target_node_id=edge.destination,
            graph_runner_id=graph_runner_id,
            order=edge.order,
        )

    nodes_to_delete = previous_graph_nodes - instance_ids
    if len(nodes_to_delete) > 0:
        await delete_component_instances_from_nodes(session, nodes_to_delete)

    for node_id in nodes_to_delete:
        await delete_node(session, node_id)
    LOGGER.info("Deleted nodes: {}".format(len(nodes_to_delete)))

    await get_agent_for_project(
        session,
        project_id=project_id,
        graph_runner_id=graph_runner_id,
    )

    return GraphUpdateResponse(graph_id=graph_runner_id)
