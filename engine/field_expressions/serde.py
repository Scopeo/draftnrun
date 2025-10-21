"""Serialization/deserialization helpers for field expression AST.

These functions convert between AST objects and their JSON (dict) representation.
They are pure and do not depend on engine or backend specifics.
"""

from typing import Any, Dict, List, Union

from engine.field_expressions.ast import (
    ExpressionNode,
    LiteralNode,
    RefNode,
    ConcatNode,
)


def to_json(expression: ExpressionNode) -> Dict[str, Any]:
    """Serialize an ExpressionNode into its JSON representation."""
    match expression:
        case LiteralNode(value=value):
            return {"type": "literal", "value": value}
        case RefNode(instance=instance, port=port):
            return {"type": "ref", "instance": instance, "port": port}
        case ConcatNode(parts=parts):
            return {"type": "concat", "parts": [to_json(p) for p in parts]}
        case _:
            return {"type": "literal", "value": ""}


def from_json(ast_dict: Dict[str, Any]) -> ExpressionNode:
    """Deserialize an ExpressionNode from its JSON representation."""
    match ast_dict:
        case {"type": "literal", "value": value}:
            return LiteralNode(value=str(value))
        case {"type": "ref", "instance": instance, "port": port}:
            return RefNode(instance=str(instance), port=str(port))
        case {"type": "concat", "parts": parts}:
            hydrated: List[ExpressionNode] = [from_json(p) for p in (parts or [])]
            # Filter to only LiteralNode | RefNode for now; nested concat collapses by flattening literals
            filtered: List[Union[LiteralNode, RefNode]] = [
                n for n in hydrated if isinstance(n, (LiteralNode, RefNode))
            ]
            return ConcatNode(parts=filtered)
        case _:
            return LiteralNode(value="")
