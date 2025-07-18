import logging
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.models import EnvType
from ada_backend.repositories.component_repository import (
    get_component_instance_by_id,
    get_component_parameter_definition_by_component_id,
    upsert_sub_component_input,
)
from ada_backend.repositories.edge_repository import get_edges, upsert_edge
from ada_backend.repositories.env_repository import (
    bind_graph_runner_to_project,
    get_env_relationship_by_graph_runner_id,
    update_graph_runner_env,
)
from ada_backend.repositories.graph_runner_repository import (
    get_component_nodes,
    get_graph_runner_for_env,
    graph_runner_exists,
    insert_graph_runner,
    upsert_component_node,
)
from ada_backend.schemas.integration_schema import GraphIntegrationSchema
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.pipeline.graph_schema import GraphDeployResponse
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance, get_relationships
from ada_backend.services.pipeline.update_pipeline_service import create_or_update_component_instance

LOGGER = logging.getLogger(__name__)


def copy_component_instance(
    session: Session,
    component_instance_id_to_copy: UUID,
    is_start_node: bool,
    project_id: UUID,
) -> UUID:
    """
    This function copies a component instance and its parameters to a new component instance.
    It returns the ID of the new component instance.
    """
    component_instance = get_component_instance(
        session,
        component_instance_id_to_copy,
        is_start_node=is_start_node,
    )
    new_composant_instance = ComponentInstanceSchema(
        name=component_instance.name,
        component_id=component_instance.component_id,
        tool_description=component_instance.tool_description,
        is_start_node=is_start_node,
        parameters=[
            PipelineParameterSchema(name=parameter.name, value=parameter.value, order=parameter.order)
            for parameter in component_instance.parameters
        ],
        integration=component_instance.integration,
    )
    print("new_composant_instance", new_composant_instance)
    return create_or_update_component_instance(session, new_composant_instance, project_id)


def clone_graph_runner(
    session: Session,
    graph_runner_id_to_copy: UUID,
    project_id: UUID,
) -> UUID:
    """
    This function copies the graph runner and all its components and edges to a new graph runner.
    """
    new_graph_runner_id = uuid4()  # Generate a new UUID for the new graph runner
    insert_graph_runner(session=session, graph_id=new_graph_runner_id)
    LOGGER.info(f"Created new graph runner with ID {new_graph_runner_id}")

    # Copy all component nodes to the new graph runner
    graph_nodes = get_component_nodes(session, graph_runner_id_to_copy)
    edges = get_edges(session, graph_runner_id_to_copy)
    ids_map = {}
    old_relationships = []
    for component_node in graph_nodes:
        # Copy the component instance into a new component instance
        print("component_node", component_node)
        new_instance_id = copy_component_instance(
            session,
            component_instance_id_to_copy=component_node.component_instance_id,
            is_start_node=component_node.is_start_node,
            project_id=project_id,
        )
        ids_map[component_node.component_instance_id] = new_instance_id

        # Insert the component node with the new ID in the new graph runner
        upsert_component_node(
            session,
            graph_runner_id=new_graph_runner_id,
            component_instance_id=ids_map[component_node.component_instance_id],
            is_start_node=component_node.is_start_node,
        )
        old_relationships.extend(
            get_relationships(
                session,
                component_node.component_instance_id,
            )
        )
    LOGGER.info(f"Copied component nodes to new graph runner with ID {new_graph_runner_id}")

    for relation in old_relationships:
        if relation.child_component_instance_id not in ids_map.keys():
            # The child component instance is not a graph node, so we need to create it
            new_child_component_instance_id = copy_component_instance(
                session,
                component_instance_id_to_copy=relation.child_component_instance_id,
                is_start_node=False,
                project_id=project_id,
            )
            ids_map[relation.child_component_instance_id] = new_child_component_instance_id
        if not (
            relation.parent_component_instance_id in ids_map.keys()
            and relation.child_component_instance_id in ids_map.keys()
        ):
            raise ValueError("Invalid relationship: component instance not found")

        # Get parameter definition ID from name
        parent = get_component_instance_by_id(session, ids_map[relation.parent_component_instance_id])
        if not parent:
            raise ValueError("Invalid relationship: parent component instance not found")
        # TODO: Refactor to repository function that takes name and component_id or with dictionary for faster lookup
        param_defs = get_component_parameter_definition_by_component_id(session, parent.component_id)
        param_def = next((p for p in param_defs if p.name == relation.parameter_name), None)
        if not param_def:
            raise ValueError(
                f"Parameter '{relation.parameter_name}' not found in "
                f"component definitions for component '{parent.component.name}'"
            )

        # Create relationship
        upsert_sub_component_input(
            session=session,
            parent_component_instance_id=ids_map[relation.parent_component_instance_id],
            child_component_instance_id=ids_map[relation.child_component_instance_id],
            parameter_definition_id=param_def.id,
            order=relation.order,
        )

    for edge in edges:
        # Copy the edge to the new graph runner
        upsert_edge(
            session,
            id=uuid4(),  # Generate a new UUID for the edge
            source_node_id=ids_map[edge.source_node_id],
            target_node_id=ids_map[edge.target_node_id],
            graph_runner_id=new_graph_runner_id,
            order=edge.order,
        )
    LOGGER.info(f"Copied edges to new graph runner with ID {new_graph_runner_id}")
    return new_graph_runner_id


def deploy_graph_service(session: Session, graph_runner_id: UUID, project_id: UUID):
    if not graph_runner_exists(session, graph_id=graph_runner_id):
        raise HTTPException(status_code=404, detail="Graph runner not found")

    env_relationship = get_env_relationship_by_graph_runner_id(session=session, graph_runner_id=graph_runner_id)
    if not env_relationship:
        raise HTTPException(status_code=404, detail="Graph runner not bound to any project")
    if env_relationship.environment == EnvType.PRODUCTION:
        raise HTTPException(status_code=400, detail="Graph runner already in production")

    previous_production_graph = get_graph_runner_for_env(
        session=session,
        project_id=project_id,
        env=EnvType.PRODUCTION,
    )
    if previous_production_graph:
        update_graph_runner_env(session, previous_production_graph.id, env=None)
        LOGGER.info(f"Updated previous production graph runner {previous_production_graph.id} to None")

    new_graph_runner_id = clone_graph_runner(
        session=session,
        graph_runner_id_to_copy=graph_runner_id,
        project_id=project_id,
    )
    bind_graph_runner_to_project(
        session, graph_runner_id=new_graph_runner_id, project_id=project_id, env=EnvType.DRAFT
    )

    update_graph_runner_env(session, graph_runner_id, env=EnvType.PRODUCTION)
    LOGGER.info(f"Updated graph runner {graph_runner_id} to production")

    return GraphDeployResponse(
        project_id=project_id,
        draft_graph_runner_id=new_graph_runner_id,
        prod_graph_runner_id=graph_runner_id,
        previous_prod_graph_runner_id=previous_production_graph.id if previous_production_graph else None,
    )
