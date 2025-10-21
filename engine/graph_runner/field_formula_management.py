"""
Graph Runner Field Formula Management Functions

This module contains field formula management functions extracted from GraphRunner to keep the
main class focused on core execution logic. These functions handle formula evaluation,
type coercion, and input resolution for field formulas.
"""

import logging
from typing import Any

from engine.graph_runner.types import Task

LOGGER = logging.getLogger(__name__)


def evaluate_formula(
    formula_json: dict[str, Any],
    target_field_name: str,
    tasks: dict[str, Task],
) -> Any:
    """Evaluate a field formula AST and return the result."""

    def evaluate_node(node_dict: dict) -> str:
        match node_dict:
            case {"type": "literal", "value": value}:
                return value

            case {"type": "ref", "instance": source_instance_id, "port": source_port_name}:
                # Topology ensures dependencies completed; fetch directly
                task_result = tasks[source_instance_id].result
                return str(task_result.data.get(source_port_name, "")) if task_result else ""

            case {"type": "concat", "parts": parts}:
                return "".join(evaluate_node(part) for part in parts)

            case {"type": "concat"}:
                # Missing parts defaults to empty string
                return ""

            case _:
                LOGGER.warning(f"Unknown node type: {node_dict.get('type')}")
                return ""

    result = evaluate_node(formula_json)
    LOGGER.debug(f"Evaluated formula for {target_field_name}: {result}")
    return result
