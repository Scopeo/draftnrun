"""
Graph Runner Field Expression Management Functions

This module contains field expression management functions extracted from GraphRunner to keep the
main class focused on core execution logic. These functions handle expression evaluation,
type coercion, and input resolution for field expressions.
"""

import logging
from typing import Any, Callable

from engine.graph_runner.types import Task
from engine.field_expressions.ast import ExpressionNode, LiteralNode, RefNode, ConcatNode, VarNode, VarType
from engine.field_expressions.errors import FieldExpressionError

LOGGER = logging.getLogger(__name__)


def evaluate_expression(
    expression: ExpressionNode,
    target_field_name: str,
    tasks: dict[str, Task],
    inject_vars: dict[VarType, dict[str, str]] | None = None,
    to_string: Callable[[Any], str] = lambda v: str(v),
) -> str:
    """Evaluate a field expression AST and return the result.

    Uses structural pattern matching over AST node classes.

    Args:
        expression: The AST to evaluate.
        target_field_name: Name of the target field (for error messages).
        tasks: Dict of completed tasks (for RefNode resolution).
        inject_vars: Dict of injected variables by VarType (e.g. {VarType.SECRETS: {uuid: value}}).
        to_string: Function to convert values to string.
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

            case VarNode(var_type=var_type, key=key):
                if inject_vars is None:
                    raise FieldExpressionError(
                        f"Injected variables missing while evaluating '{target_field_name}': "
                        f"cannot resolve @{{ ${var_type.value}.{key} }}"
                    )

                if var_type not in inject_vars:
                    raise FieldExpressionError(
                        f"Variable type '{var_type.value}' not found in inject_vars "
                        f"while evaluating '{target_field_name}'"
                    )

                var_data = inject_vars[var_type]
                if key not in var_data:
                    raise FieldExpressionError(
                        f"Key '{key}' not found in '{var_type.value}' while evaluating '{target_field_name}'"
                    )

                return to_string(var_data[key])

            case ConcatNode(parts=parts):
                return "".join(evaluate_node(part) for part in parts)

            case _:
                raise FieldExpressionError(f"Unknown node type: {node}")

    result = evaluate_node(expression)
    LOGGER.debug(f"Evaluated expression for {target_field_name}: {result}")
    return result
