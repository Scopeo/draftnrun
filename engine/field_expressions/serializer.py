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
    RefNode,
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


def from_json(ast_dict: Dict[str, Any]) -> ExpressionNode:
    """Deserialize an ExpressionNode from its JSON representation."""
    match ast_dict:
        case {"type": "literal", "value": value}:
            return LiteralNode(value=str(value))
        case {"type": "ref", "instance": instance, "port": port, **rest}:
            return RefNode(instance=str(instance), port=str(port), key=rest.get("key"))
        case {"type": "concat", "parts": parts}:
            hydrated: List[ExpressionNode] = [from_json(p) for p in (parts or [])]
            # Filter to only LiteralNode | RefNode for now; nested concat collapses by flattening literals
            filtered: List[Union[LiteralNode, RefNode]] = [
                n for n in hydrated if isinstance(n, (LiteralNode, RefNode))
            ]
            return ConcatNode(parts=filtered)
        case {"type": "json_build", "template": template, "refs": refs}:
            parsed_refs = {}
            for key, ref_json in refs.items():
                parsed_ref = from_json(ref_json)
                if isinstance(parsed_ref, RefNode):
                    parsed_refs[key] = parsed_ref
                else:
                    # If not a RefNode, skip it (only RefNodes allowed in json_build)
                    pass
            return JsonBuildNode(template=template, refs=parsed_refs)
        case _:
            return LiteralNode(value="")
