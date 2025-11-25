"""
Graph Runner Field Expression Management Functions

This module contains field expression management functions extracted from GraphRunner to keep the
main class focused on core execution logic. These functions handle expression evaluation,
type coercion, and input resolution for field expressions.
"""

import logging
from typing import Any, Callable

from engine.graph_runner.types import Task
from engine.field_expressions.ast import ExpressionNode, LiteralNode, RefNode, ConcatNode, ExternalRefNode
from engine.field_expressions.errors import FieldExpressionError

LOGGER = logging.getLogger(__name__)


def evaluate_expression(
    expression: ExpressionNode,
    target_field_name: str,
    tasks: dict[str, Task],
    external_context: dict[str, Any] | None = None,
    to_string: Callable[[Any], str] = lambda v: str(v),
) -> str:
    """Evaluate a field expression AST and return the result.

    Uses structural pattern matching over AST node classes.
    """

    def evaluate_node(node: ExpressionNode) -> str:
        match node:
            case LiteralNode(value=value):
                return value

            case RefNode(instance=source_instance_id, port=source_port_name, key=key):
                task = tasks.get(source_instance_id)
                task_result = task.result if task else None
                if not task_result:
                    raise FieldExpressionError(
                        f"Upstream result missing while evaluating '{target_field_name}': "
                        f"{source_instance_id}.{source_port_name} has no completed result"
                    )
                if source_port_name not in task_result.data:
                    raise FieldExpressionError(
                        f"Upstream port missing while evaluating '{target_field_name}': "
                        f"'{source_port_name}' not found in output of {source_instance_id}"
                    )
                raw_value = task_result.data[source_port_name]

                if key:
                    if not isinstance(raw_value, dict):
                        raise FieldExpressionError(
                            f"Key extraction '::{key}' cannot be used on {source_instance_id}.{source_port_name}: "
                            f"port value is not a dict, got {type(raw_value)}"
                        )
                    if key not in raw_value:
                        raise FieldExpressionError(
                            f"Key '{key}' not found in dict from {source_instance_id}.{source_port_name}"
                        )
                    raw_value = raw_value[key]

                return to_string(raw_value)

            case ExternalRefNode(source=source, key=key):
                if not external_context:
                    raise FieldExpressionError(
                        f"External context missing while evaluating '{target_field_name}': "
                        f"cannot resolve reference @{{ ${source}.{key} }}"
                    )
                
                if source not in external_context:
                    raise FieldExpressionError(
                        f"External source '{source}' not found in context while evaluating '{target_field_name}'"
                    )
                
                source_data = external_context[source]
                if not isinstance(source_data, dict):
                     raise FieldExpressionError(
                        f"External source '{source}' is not a dictionary, got {type(source_data)}"
                    )

                if key not in source_data:
                    raise FieldExpressionError(
                        f"Key '{key}' not found in external source '{source}' while evaluating '{target_field_name}'"
                    )
                
                return to_string(source_data[key])

            case ConcatNode(parts=parts):
                return "".join(evaluate_node(part) for part in parts)

            case _:
                raise FieldExpressionError(f"Unknown node type: {node}")

    result = evaluate_node(expression)
    LOGGER.debug(f"Evaluated expression for {target_field_name}: {result}")
    return result
