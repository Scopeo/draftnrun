import copy
from typing import Any
from uuid import UUID, uuid4

from ada_backend.schemas.pipeline.base import ComponentInstanceSchema, ComponentRelationshipSchema
from ada_backend.schemas.pipeline.graph_schema import (
    EdgeSchema,
    GraphComponentFileSchema,
    GraphGetResponse,
    GraphGetV2Response,
    GraphMapNodeRefSchema,
    GraphMapSchema,
    GraphSaveV2Schema,
    GraphUpdateSchema,
)
from ada_backend.services.errors import GraphValidationError


def _node_ref_to_instance_id(
    ref: GraphMapNodeRefSchema,
    file_key_to_instance_id: dict[str, UUID],
    known_instance_ids: set[UUID],
) -> UUID:
    if ref.id:
        if ref.id not in known_instance_ids:
            raise GraphValidationError(f"Referenced id '{ref.id}' is not part of the current graph payload")
        return ref.id
    if not ref.file_key:
        raise GraphValidationError("Node reference must include either 'id' or 'file_key'")
    if ref.file_key not in file_key_to_instance_id:
        raise GraphValidationError(f"Unknown file_key '{ref.file_key}' in graph map reference")
    return file_key_to_instance_id[ref.file_key]


def _resolve_expression_file_keys(expr: Any, file_key_to_instance_id: dict[str, UUID]) -> Any:
    if isinstance(expr, list):
        resolved = [_resolve_expression_file_keys(item, file_key_to_instance_id) for item in expr]
        return expr if all(r is o for r, o in zip(resolved, expr)) else resolved
    if not isinstance(expr, dict):
        return expr
    if expr.get("type") == "ref" and "file_key" in expr and "instance" not in expr:
        fk = expr["file_key"]
        if fk not in file_key_to_instance_id:
            raise GraphValidationError(f"Unknown file_key '{fk}' in field expression ref")
        resolved = {k: v for k, v in expr.items() if k != "file_key"}
        resolved["instance"] = str(file_key_to_instance_id[fk])
        return resolved
    resolved = {}
    changed = False
    for k, v in expr.items():
        new_v = _resolve_expression_file_keys(v, file_key_to_instance_id)
        resolved[k] = new_v
        if new_v is not v:
            changed = True
    return resolved if changed else expr


def _resolve_input_port_file_keys(
    input_port_instances: list[dict],
    file_key_to_instance_id: dict[str, UUID],
) -> list[dict]:
    resolved = []
    for port in input_port_instances:
        fe = port.get("field_expression")
        if not fe or "expression_json" not in fe:
            resolved.append(port)
            continue
        new_expr = _resolve_expression_file_keys(fe["expression_json"], file_key_to_instance_id)
        if new_expr is fe["expression_json"]:
            resolved.append(port)
        else:
            port_copy = copy.deepcopy(port)
            port_copy["field_expression"]["expression_json"] = new_expr
            resolved.append(port_copy)
    return resolved


def graph_save_v2_to_graph_update(payload: GraphSaveV2Schema) -> GraphUpdateSchema:
    component_by_file_key: dict[str, GraphComponentFileSchema] = {comp.file_key: comp for comp in payload.components}
    if len(component_by_file_key) != len(payload.components):
        raise GraphValidationError("Duplicate component file_key in components payload")

    file_key_to_instance_id: dict[str, UUID] = {}
    instance_ids: set[UUID] = set()

    node_component_pairs: list[tuple] = []
    for node in payload.graph_map.nodes:
        if not node.file_key:
            raise GraphValidationError("Each node in graph_map must have a file_key when saving")
        component_file = component_by_file_key.get(node.file_key)
        if component_file is None:
            raise GraphValidationError(f"Missing component file for node file_key '{node.file_key}'")

        resolved_id = node.instance_id or component_file.id or uuid4()
        if node.file_key in file_key_to_instance_id:
            raise GraphValidationError(
                f"Duplicate file_key '{node.file_key}' in graph_map.nodes: "
                f"instance ids {file_key_to_instance_id[node.file_key]} and {resolved_id}"
            )
        file_key_to_instance_id[node.file_key] = resolved_id
        instance_ids.add(resolved_id)
        node_component_pairs.append((node, component_file, resolved_id))

    component_instances: list[ComponentInstanceSchema] = []
    for node, component_file, resolved_id in node_component_pairs:
        resolved_ports = _resolve_input_port_file_keys(component_file.input_port_instances, file_key_to_instance_id)
        component_instances.append(
            ComponentInstanceSchema(
                id=resolved_id,
                name=node.label,
                is_start_node=node.is_start_node,
                component_id=component_file.component_id,
                component_version_id=component_file.component_version_id,
                parameters=component_file.parameters,
                input_port_instances=resolved_ports,
                integration=component_file.integration,
                tool_description_override=component_file.tool_description_override,
                port_configurations=component_file.port_configurations,
            )
        )

    edges: list[EdgeSchema] = []
    for edge in payload.graph_map.edges:
        source_instance_id = _node_ref_to_instance_id(edge.from_node, file_key_to_instance_id, instance_ids)
        target_instance_id = _node_ref_to_instance_id(edge.to_node, file_key_to_instance_id, instance_ids)
        edges.append(
            EdgeSchema(
                id=edge.id or uuid4(),
                origin=source_instance_id,
                destination=target_instance_id,
                order=edge.order,
            )
        )

    relationships: list[ComponentRelationshipSchema] = []
    for relation in payload.graph_map.relationships:
        parent_id = _node_ref_to_instance_id(relation.parent, file_key_to_instance_id, instance_ids)
        child_id = _node_ref_to_instance_id(relation.child, file_key_to_instance_id, instance_ids)
        relationships.append(
            ComponentRelationshipSchema(
                parent_component_instance_id=parent_id,
                child_component_instance_id=child_id,
                parameter_name=relation.parameter_name,
                order=relation.order,
            )
        )

    return GraphUpdateSchema(
        component_instances=component_instances,
        relationships=relationships,
        edges=edges,
        last_edited_time=payload.last_edited_time,
    )


def graph_get_to_graph_v2_response(graph: GraphGetResponse) -> GraphGetV2Response:
    nodes = []
    for instance in graph.component_instances:
        nodes.append({
            "instance_id": instance.id,
            "label": instance.name,
            "is_start_node": instance.is_start_node,
        })

    graph_map = GraphMapSchema(
        nodes=nodes,
        edges=[
            {
                "id": edge.id,
                "from": {"id": edge.origin},
                "to": {"id": edge.destination},
                "order": edge.order,
            }
            for edge in graph.edges
        ],
        relationships=[
            {
                "parent": {"id": relation.parent_component_instance_id},
                "child": {"id": relation.child_component_instance_id},
                "parameter_name": relation.parameter_name,
                "order": relation.order,
            }
            for relation in graph.relationships
        ],
    )
    return GraphGetV2Response(
        graph_map=graph_map,
        tag_name=graph.tag_name,
        change_log=graph.change_log,
        last_edited_time=graph.last_edited_time,
        last_edited_user_id=graph.last_edited_user_id,
    )
