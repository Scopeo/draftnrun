"""
Graph Runner Field Expression Management Functions

This module contains field expression management functions extracted from GraphRunner to keep the
main class focused on core execution logic. These functions handle expression evaluation,
type coercion, and input resolution for field expressions.
"""

import logging
from typing import Any, Callable

from engine.field_expressions.ast import ConcatNode, ExpressionNode, JsonBuildNode, LiteralNode, RefNode
from engine.field_expressions.errors import FieldExpressionError
from engine.graph_runner.types import Task

LOGGER = logging.getLogger(__name__)


def evaluate_expression(
    expression: ExpressionNode,
    target_field_name: str,
    tasks: dict[str, Task],
    to_string: Callable[[Any], str] = lambda v: str(v),
) -> str | dict | list:
    """Evaluate a field expression AST and return the result.

    Uses structural pattern matching over AST node classes.
    
    Returns:
        - str for LiteralNode, RefNode (stringified), and ConcatNode
        - dict or list for JsonBuildNode (preserves structure)
    """

    def evaluate_ref_as_object(ref: RefNode) -> Any:
        """Evaluate a RefNode and return the raw value (not stringified)."""
        task = tasks.get(ref.instance)
        task_result = task.result if task else None
        if not task_result:
            raise FieldExpressionError(
                f"Upstream result missing while evaluating '{target_field_name}': "
                f"{ref.instance}.{ref.port} has no completed result"
            )
        if ref.port not in task_result.data:
            raise FieldExpressionError(
                f"Upstream port missing while evaluating '{target_field_name}': "
                f"'{ref.port}' not found in output of {ref.instance}"
            )
        raw_value = task_result.data[ref.port]

        if ref.key:
            if not isinstance(raw_value, dict):
                raise FieldExpressionError(
                    f"Key extraction '::{ref.key}' cannot be used on {ref.instance}.{ref.port}: "
                    f"port value is not a dict, got {type(raw_value)}"
                )
            if ref.key not in raw_value:
                raise FieldExpressionError(
                    f"Key '{ref.key}' not found in dict from {ref.instance}.{ref.port}"
                )
            raw_value = raw_value[ref.key]

        return raw_value

    def substitute_in_template(obj: Any, refs: dict[str, Any]) -> Any:
        """Recursively substitute placeholder strings with ref values in template."""
        if isinstance(obj, str):
            # If the string is a placeholder, replace it
            return refs.get(obj, obj)
        elif isinstance(obj, dict):
            return {key: substitute_in_template(val, refs) for key, val in obj.items()}
        elif isinstance(obj, list):
            return [substitute_in_template(item, refs) for item in obj]
        else:
            return obj

    def evaluate_node(node: ExpressionNode) -> str:
        """Evaluate node to string (for concat/ref/literal)."""
        match node:
            case LiteralNode(value=value):
                return value

            case RefNode() as ref:
                raw_value = evaluate_ref_as_object(ref)
                return to_string(raw_value)

            case ConcatNode(parts=parts):
                return "".join(evaluate_node(part) for part in parts)

            case _:
                raise FieldExpressionError(f"Unknown node type: {node}")

    # Handle JsonBuildNode specially (returns object, not string)
    match expression:
        case JsonBuildNode(template=template, refs=ref_nodes):
            # Evaluate all refs to their actual values (preserving types)
            evaluated_refs = {}
            for placeholder, ref_node in ref_nodes.items():
                evaluated_refs[placeholder] = evaluate_ref_as_object(ref_node)
            
            # Substitute placeholders in template
            result = substitute_in_template(template, evaluated_refs)
            LOGGER.debug(f"Evaluated JSON build expression for {target_field_name}")
            return result
        
        case _:
            # For all other nodes, evaluate to string
            result = evaluate_node(expression)
            LOGGER.debug(f"Evaluated expression for {target_field_name}: {result}")
            return result
