from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ada_backend.schemas.pipeline.base import ComponentRelationshipSchema
from ada_backend.schemas.pipeline.graph_schema import EdgeSchema, GraphLoadResponse
from ada_backend.schemas.pipeline.get_pipeline_schema import ComponentInstanceReadSchema
from ada_backend.schemas.parameter_schema import ParameterKind
from ada_backend.services.graph.get_graph_service import get_graph_service
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance
from ada_backend.services.field_expression_remap_service import (
    remap_instance_ids_in_expression,
)
from engine.field_expressions.parser import parse_expression, unparse_expression


def instanciate_copy_component_instance(
    session: Session,
    component_instance_id_to_copy: UUID,
    is_start_node: bool,
) -> ComponentInstanceReadSchema:
    component_instance_to_copy = get_component_instance(
        session,
        component_instance_id_to_copy,
        is_start_node=is_start_node,
    )
    if not component_instance_to_copy:
        raise ValueError("Component instance not found")
    return component_instance_to_copy.model_copy(update={"id": uuid4(), "field_expressions": []})


def load_copy_graph_service(
    session: Session,
    project_id_to_copy: UUID,
    graph_runner_id_to_copy: UUID,
) -> GraphLoadResponse:
    graph_get_response = get_graph_service(
        session=session, project_id=project_id_to_copy, graph_runner_id=graph_runner_id_to_copy
    )
    component_instance_map: dict[UUID, ComponentInstanceReadSchema] = {}
    for component_instance_to_copy in graph_get_response.component_instances:
        source_id = component_instance_to_copy.id
        if source_id is None:
            raise ValueError("Component instance missing id in GET response")
        component_instance = component_instance_to_copy.model_copy(update={"id": uuid4(), "field_expressions": []})
        component_instance_map[source_id] = component_instance

    if graph_get_response.component_instances:
        source_instance_ids = [ci.id for ci in graph_get_response.component_instances if ci.id is not None]
        id_mapping: dict[UUID, UUID] = {}
        for source_id in source_instance_ids:
            target_id = component_instance_map[source_id].id
            if target_id is None:
                raise ValueError("Target component instance missing id during load-copy")
            id_mapping[source_id] = target_id

        id_mapping_str: dict[str, str] = {str(src): str(dst) for src, dst in id_mapping.items()}
        for source_instance_id, target_instance in component_instance_map.items():
            # Update parameters[kind='input'] expression texts to use remapped instance IDs
            updated_params = []
            for param in target_instance.parameters:
                if getattr(param, "kind", None) == ParameterKind.INPUT and param.value is not None:
                    expression_text = str(param.value)
                    ast = parse_expression(expression_text)
                    remapped_ast = remap_instance_ids_in_expression(ast, id_mapping_str)
                    remapped_text = unparse_expression(remapped_ast)
                    param = param.model_copy(update={"value": remapped_text})
                updated_params.append(param)
            target_instance.parameters = updated_params

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

        parent_new_id = component_instance_map[old_relation.parent_component_instance_id].id
        child_new_id = component_instance_map[old_relation.child_component_instance_id].id
        if parent_new_id is None or child_new_id is None:
            raise ValueError("New relationship endpoint missing id during load-copy")
        load_copy_relationships.append(
            ComponentRelationshipSchema(
                parent_component_instance_id=parent_new_id,
                child_component_instance_id=child_new_id,
                parameter_name=old_relation.parameter_name,
                order=old_relation.order,
            )
        )

    load_copy_edges: list[EdgeSchema] = []
    for edge in graph_get_response.edges:
        origin_new_id = component_instance_map[edge.origin].id
        destination_new_id = component_instance_map[edge.destination].id
        if origin_new_id is None or destination_new_id is None:
            raise ValueError("New edge endpoint missing id during load-copy")
        load_copy_edges.append(
            EdgeSchema(
                id=uuid4(),  # Generate a new UUID for the edge
                origin=origin_new_id,
                destination=destination_new_id,
                order=edge.order,
            )
        )
    return GraphLoadResponse(
        component_instances=list(component_instance_map.values()),
        relationships=load_copy_relationships,
        edges=load_copy_edges,
    )
