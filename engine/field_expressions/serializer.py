"""Serialization/deserialization helpers for field expression AST.

These functions convert between AST objects and their JSON (dict) representation.
They are pure and do not depend on engine or backend specifics.
"""

from typing import Any, Dict, List, Union

from engine.field_expressions.ast import (
    ConcatNode,
    ExpressionNode,
    JsonBuildNode,
    LiteralNode,
    OAuthNode,
    RefNode,
    VarNode,
)


def to_json(expression: ExpressionNode) -> Dict[str, Any]:
    """Serialize an ExpressionNode into its JSON representation."""
    match expression:
        case LiteralNode(value=value):
            return {"type": "literal", "value": value}
        case RefNode(instance=instance, port=port, key=key):
            result = {"type": "ref", "instance": instance, "port": port}
            if key is not None:
                result["key"] = key
            return result
        case VarNode(name=name):
            return {"type": "var", "name": name}
        case OAuthNode(definition_id=definition_id):
            return {"type": "oauth", "definition_id": definition_id}
        case ConcatNode(parts=parts):
            return {"type": "concat", "parts": [to_json(p) for p in parts]}
        case JsonBuildNode(template=template, refs=refs):
            return {
                "type": "json_build",
                "template": template,
                "refs": {key: to_json(ref) for key, ref in refs.items()},
            }
        case _:
            return {"type": "literal", "value": ""}


def is_serialized_expression_ast(value: Dict[str, Any]) -> bool:
    """Return True when a dict matches a serialized ExpressionNode shape.

    TODO: If we add a JsonLiteralNode (or typed literal nodes) we can stop overloading
    LiteralNode(value: str) for raw JSON literals and make this distinction explicit.
    """
    match value:
        case {"type": "literal", "value": _}:
            return True
        case {"type": "ref", "instance": _, "port": _, **rest}:
            return "key" not in rest or rest["key"] is None or isinstance(rest["key"], str)
        case {"type": "var", "name": _}:
            return True
        case {"type": "oauth", "definition_id": _}:
            return True
        case {"type": "concat", "parts": list(parts)}:
            return all(isinstance(part, dict) and is_serialized_expression_ast(part) for part in parts)
        case {"type": "json_build", "template": _, "refs": dict(refs)}:
            return all(
                isinstance(ref_json, dict) and is_serialized_expression_ast(ref_json)
                for ref_json in refs.values()
            )
        case _:
            return False


def from_json(ast_dict: Dict[str, Any]) -> ExpressionNode:
    """Deserialize an ExpressionNode from its JSON representation."""
    match ast_dict:
        case {"type": "literal", "value": value}:
            return LiteralNode(value=str(value))
        case {"type": "ref", "instance": instance, "port": port, **rest}:
            return RefNode(instance=str(instance), port=str(port), key=rest.get("key"))
        case {"type": "var", "name": name}:
            return VarNode(name=str(name))
        case {"type": "oauth", "definition_id": definition_id}:
            return OAuthNode(definition_id=str(definition_id))
        case {"type": "concat", "parts": parts}:
            hydrated: List[ExpressionNode] = [from_json(p) for p in (parts or [])]
            filtered: List[Union[LiteralNode, RefNode, VarNode]] = [
                n for n in hydrated if isinstance(n, (LiteralNode, RefNode, VarNode))
            ]
            return ConcatNode(parts=filtered)
        case {"type": "json_build", "template": template, "refs": refs}:
            parsed_refs = {}
            for key, ref_json in refs.items():
                parsed_ref = from_json(ref_json)
                if isinstance(parsed_ref, (RefNode, VarNode)):
                    parsed_refs[key] = parsed_ref
            return JsonBuildNode(template=template, refs=parsed_refs)
        case _:
            raise ValueError(
                "Expected a serialized field expression AST dict, "
                f"got unsupported structure: {ast_dict!r}"
            )
