from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema, ComponentRelationshipSchema
from ada_backend.schemas.pipeline.graph_schema import EdgeSchema, GraphLoadResponse
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance


def instanciate_copy_component_instance(
    session: Session,
    component_instance_id_to_copy: UUID,
    is_start_node: bool,
) -> ComponentInstanceSchema:
    component_instance_to_copy = get_component_instance(
        session,
        component_instance_id_to_copy,
        is_start_node=is_start_node,
    )
    if not component_instance_to_copy:
        raise ValueError("Component instance not found")
    return ComponentInstanceSchema(
        id=uuid4(),
        name=component_instance_to_copy.name,
        is_start_node=component_instance_to_copy.is_start_node,
        component_id=component_instance_to_copy.component_id,
        tool_description=component_instance_to_copy.tool_description,
        parameters=[
            PipelineParameterSchema(name=param.name, value=param.value, order=param.order)
            for param in component_instance_to_copy.parameters
        ],
        integration=component_instance_to_copy.integration,
    )


def load_copy_graph_service(
    session: Session,
    project_id_to_copy: UUID,
    graph_runner_id_to_copy: UUID,
) -> GraphLoadResponse:
    graph_get_response = get_graph_service(
        session=session, project_id=project_id_to_copy, graph_runner_id=graph_runner_id_to_copy
    )
    component_instance_map: dict[UUID, ComponentInstanceSchema] = {}
    for component_instance_to_copy in graph_get_response.component_instances:
        component_instance = ComponentInstanceSchema(
            id=uuid4(),
            name=component_instance_to_copy.name,
            is_start_node=component_instance_to_copy.is_start_node,
            component_id=component_instance_to_copy.component_id,
            tool_description=component_instance_to_copy.tool_description,
            parameters=[
                PipelineParameterSchema(name=param.name, value=param.value, order=param.order)
                for param in component_instance_to_copy.parameters
            ],
            integration=component_instance_to_copy.integration,
        )
        component_instance_map[component_instance_to_copy.id] = component_instance

    load_copy_relationships: list[ComponentRelationshipSchema] = []
    for old_relation in graph_get_response.relationships:
        if old_relation.child_component_instance_id not in component_instance_map.keys():
            # The child component instance is not a graph node, so we need to create it
            new_child_component_instance = instanciate_copy_component_instance(
                session,
                component_instance_id_to_copy=old_relation.child_component_instance_id,
                is_start_node=False,
            )
            component_instance_map[old_relation.child_component_instance_id] = new_child_component_instance
        if not (
            old_relation.parent_component_instance_id in component_instance_map.keys()
            and old_relation.child_component_instance_id in component_instance_map.keys()
        ):
            raise ValueError("Invalid relationship: component instance not found")

        load_copy_relationships.append(
            ComponentRelationshipSchema(
                id=uuid4(),
                parent_component_instance_id=component_instance_map[old_relation.parent_component_instance_id].id,
                child_component_instance_id=component_instance_map[old_relation.child_component_instance_id].id,
                parameter_name=old_relation.parameter_name,
                order=old_relation.order,
            )
        )

    load_copy_edges: list[EdgeSchema] = []
    for edge in graph_get_response.edges:
        load_copy_edges.append(
            EdgeSchema(
                id=uuid4(),  # Generate a new UUID for the edge
                origin=component_instance_map[edge.origin].id,
                destination=component_instance_map[edge.destination].id,
                order=edge.order,
            )
        )
    return GraphLoadResponse(
        component_instances=list(component_instance_map.values()),
        relationships=load_copy_relationships,
        edges=load_copy_edges,
    )
