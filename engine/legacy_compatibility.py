"""
LEGACY COMPATIBILITY MODULE - DELETE AFTER MIGRATION COMPLETE

This module contains all legacy/retro-compatibility code that should be deleted
once all components are migrated to use the new multi-port I/O system.

IMPORTANT: This entire module should be deleted after migration is complete.
All functions and classes here are temporary solutions for unmigrated components.
"""

import logging
from typing import Type, Optional, Any
from pydantic import BaseModel

from engine.agent.types import ChatMessage, AgentPayload, NodeData
from engine.trace.serializer import serialize_to_json
from ada_backend.database.seed.utils import COMPONENT_UUIDS

LOGGER = logging.getLogger(__name__)


# ============================================================================
# LEGACY TYPE DISCOVERY FUNCTIONS
# ============================================================================


def get_unmigrated_output_type(component, port_name: str) -> Type | None:
    """Get output type for unmigrated components using known patterns.

    LEGACY FUNCTION: This is a temporary solution for unmigrated components.
    DELETE THIS FUNCTION once all components are migrated to use Pydantic schemas.

    Most unmigrated components return AgentPayload structure, except Input component.
    """
    # AgentPayload pattern (most unmigrated components)
    AGENT_PAYLOAD_PATTERN = {
        "messages": list[ChatMessage],
        "artifacts": dict,
        "error": Optional[str],
        "is_final": Optional[bool],
    }

    # Special case: Start/Input component has different pattern
    # Start/Input component actually outputs list[dict], not list[ChatMessage]
    component_id = component.id
    if component_id in [COMPONENT_UUIDS["start"]]:
        return {"messages": list[dict]}.get(port_name)

    # Default: All other unmigrated components use AgentPayload pattern
    return AGENT_PAYLOAD_PATTERN.get(port_name)


# ============================================================================
# LEGACY COMPONENT SCHEMA METHODS
# ============================================================================


def create_legacy_input_schema() -> Type[BaseModel]:
    """Create legacy input schema for unmigrated Start/Input component.

    LEGACY FUNCTION: DELETE after Start/Input component is migrated to Agent base class.
    """

    class InputSchema(BaseModel):
        input_data: Any

    return InputSchema


def create_legacy_input_output_schema() -> Type[BaseModel]:
    """Create legacy output schema for unmigrated Input component.

    LEGACY FUNCTION: DELETE after Input component is migrated to Agent base class.

    Note: Input component actually outputs list[dict], not list[ChatMessage].
    """

    class OutputSchema(BaseModel):
        messages: list[dict]

    return OutputSchema


# ============================================================================
# LEGACY DATA CONVERSION FUNCTIONS
# ============================================================================


def normalize_output_to_node_data(result: Any, run_context: dict[str, Any]) -> NodeData:
    """Backward-compatibility: normalize runnable outputs to NodeData.

    LEGACY FUNCTION: DELETE after all components return NodeData directly.

    Supports NodeData, AgentPayload, and dict outputs from legacy components.
    """
    if isinstance(result, NodeData):
        return result
    if isinstance(result, AgentPayload):
        return NodeData(data=result.model_dump(exclude_unset=True, exclude_none=True), ctx=run_context)
    if isinstance(result, dict):
        return NodeData(data=result, ctx=run_context)
    raise TypeError(f"Unsupported runnable output type: {type(result)}")


def convert_typed_output_to_legacy(output_model: BaseModel) -> AgentPayload:
    """Convert typed output to legacy AgentPayload format.

    LEGACY FUNCTION: DELETE after all components use new I/O system.
    """
    data = output_model.model_dump()
    message: ChatMessage
    content = data.get("output")
    if isinstance(content, ChatMessage):
        message = content
    elif isinstance(content, str):
        message = ChatMessage(role="assistant", content=content)
    else:
        # Fallback when no 'output' string provided (e.g., GmailSender)
        message = ChatMessage(role="assistant", content=serialize_to_json(data, shorten_string=True))

    return AgentPayload(
        messages=[message],
        is_final=bool(data.get("is_final", False)),
        artifacts=data.get("artifacts", {}) or {},
    )


def convert_legacy_to_node_data(payload: AgentPayload | dict, ctx: dict) -> NodeData:
    """Convert legacy payload to NodeData.

    LEGACY FUNCTION: DELETE after all components use new I/O system.
    """
    if isinstance(payload, AgentPayload):
        data = {
            "output": payload.last_message.content if payload.messages else None,
            "is_final": payload.is_final,
            "artifacts": payload.artifacts,
        }
    else:
        data = payload
    return NodeData(data=data, ctx=ctx)


def collect_inputs_from_legacy(args: tuple, kwargs: dict) -> dict:
    """Collect inputs from legacy argument patterns.

    LEGACY FUNCTION: DELETE after all components use new I/O system.
    """
    data: dict[str, Any] = {}
    if kwargs:
        data.update(kwargs)
    for item in args:
        if isinstance(item, AgentPayload):
            data.update(item.model_dump(exclude_unset=True, exclude_none=True))
        elif isinstance(item, dict):
            data.update(item)
    return data


# ============================================================================
# LEGACY OUTPUT COLLECTION
# ============================================================================


def pick_canonical_output(node_id: str, node_data: NodeData, runnables: dict) -> str:
    """Extract canonical output from NodeData for legacy compatibility.

    LEGACY FUNCTION: DELETE after multi-port I/O system is fully adopted.
    """
    runnable = runnables.get(node_id)
    preferred_key: str | None = None
    if runnable and hasattr(runnable, "get_canonical_ports"):
        try:
            ports = runnable.get_canonical_ports()
            preferred_key = ports.get("output") if isinstance(ports, dict) else None
        except Exception:
            preferred_key = None
    data = node_data.data or {}
    value = None
    if preferred_key and preferred_key in data:
        value = data.get(preferred_key)
    if value is None:
        value = data.get("output", data.get("response"))

    # Handle plain strings
    if isinstance(value, str):
        return value

    # Fallback: serialize the value of the port, or the whole data dict if no value found
    if value is not None:
        return serialize_to_json(value, shorten_string=True)

    return serialize_to_json(data, shorten_string=True)


def collect_legacy_outputs(graph, tasks: dict, input_node_id: str, runnables: dict) -> AgentPayload:
    """Collect outputs in legacy AgentPayload format.

    LEGACY FUNCTION: DELETE after multi-port I/O system is fully adopted.
    """
    leaf_nodes: list[str] = []
    for node_id in graph.nodes():
        if graph.out_degree(node_id) == 0 and node_id != input_node_id:
            leaf_nodes.append(node_id)

    leaf_pairs: list[tuple[str, NodeData]] = []
    for node_id in leaf_nodes:
        task = tasks.get(node_id)
        if task and task.state.value == "completed" and task.result is not None:
            leaf_pairs.append((node_id, task.result))

    if not leaf_pairs:
        return AgentPayload(messages=[ChatMessage(role="assistant", content="")])

    if len(leaf_pairs) == 1:
        node_id, nd = leaf_pairs[0]
        content = pick_canonical_output(node_id, nd, runnables)
        data = nd.data or {}
        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=content)],
            is_final=bool(data.get("is_final", False)),
            artifacts=data.get("artifacts", {}) or {},
        )

    # Multiple leaves: concatenate
    message_content = ""
    for i, (node_id, nd) in enumerate(leaf_pairs, start=1):
        content = pick_canonical_output(node_id, nd, runnables)
        message_content += f"Result from output {i}:\n{content}\n\n"
    return AgentPayload(messages=[ChatMessage(role="assistant", content=message_content.strip())])
