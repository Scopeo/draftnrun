from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.field_expression_repository import get_field_expressions_for_instances
from ada_backend.schemas.pipeline.field_expression_schema import FieldExpressionUpdateSchema
from engine.field_expressions.ast import ExpressionNode, RefNode
from engine.field_expressions.serializer import from_json as expr_from_json
from engine.field_expressions.parser import unparse_expression
from engine.field_expressions.traversal import map_expression


def remap_instance_ids_in_expression(
    expr: ExpressionNode,
    id_mapping: dict[str, str],
) -> ExpressionNode:
    """Remap component instance IDs in a field expression AST.

    Args:
        expr: The expression AST to transform
        id_mapping: Dictionary mapping source instance ID (str) to target instance ID (str)

    Returns:
        A new expression AST with remapped instance IDs
    """

    def transform(node: ExpressionNode) -> ExpressionNode:
        if not isinstance(node, RefNode):
            return node
        remapped_instance_id = id_mapping.get(node.instance, node.instance)
        return RefNode(instance=remapped_instance_id, port=node.port, key=node.key)

    return map_expression(expr, transform)


def remap_field_expressions_for_cloning(
    session: Session,
    source_instance_ids: list[UUID],
    id_mapping: dict[UUID, UUID],
) -> dict[UUID, list[FieldExpressionUpdateSchema]]:
    """Read field expressions from DB, remap instance IDs, and return remapped expressions.

    Args:
        session: Database session
        source_instance_ids: List of source component instance IDs to fetch expressions for
        id_mapping: Dictionary mapping source instance ID (UUID) to target instance ID (UUID)

    Returns:
        Dictionary mapping source instance ID to list of remapped field expressions
    """
    field_expression_records = get_field_expressions_for_instances(session, source_instance_ids)
    expressions_by_source_id: dict[UUID, list] = {}
    for field_expr_record in field_expression_records:
        expressions_by_source_id.setdefault(field_expr_record.component_instance_id, []).append(field_expr_record)

    id_mapping_str: dict[str, str] = {str(source_id): str(target_id) for source_id, target_id in id_mapping.items()}

    remapped_expressions_by_source_id: dict[UUID, list[FieldExpressionUpdateSchema]] = {}
    for source_instance_id, field_expr_records in expressions_by_source_id.items():
        remapped_expressions: list[FieldExpressionUpdateSchema] = []
        for field_expr_record in field_expr_records:
            original_ast = expr_from_json(field_expr_record.expression_json)
            remapped_ast = remap_instance_ids_in_expression(original_ast, id_mapping_str)
            if not field_expr_record.port_definition:
                continue
            expr_text = unparse_expression(remapped_ast)
            remapped_expressions.append(
                FieldExpressionUpdateSchema(
                    port_definition_id=field_expr_record.port_definition_id,
                    expression_text=expr_text,
                )
            )
        remapped_expressions_by_source_id[source_instance_id] = remapped_expressions

    return remapped_expressions_by_source_id
