"""Shared utilities for MCP tools (Local and Remote)."""

import json
from typing import Any, Callable

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from engine.components.types import ToolDescription

DEFAULT_MCP_TOOL_DESCRIPTION = ToolDescription(
    name="mcp_tool",
    description="MCP tool description. Please, ignore this. MCP tools are fetched from the server.",
    tool_properties={},
    required_tool_properties=[],
)


class MCPToolInputs(BaseModel):
    """Shared input schema for both Local and Remote MCP tools."""

    tool_name: str = Field(
        description="Name of the MCP tool to call.",
        json_schema_extra={"disabled_as_input": True, "is_tool_input": False},
    )
    tool_arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to pass to the MCP tool.",
        json_schema_extra={"disabled_as_input": True, "is_tool_input": False},
    )
    # TODO: Remove this after function-calling refactor
    model_config = {"extra": "allow"}


class MCPToolOutputs(BaseModel):
    """Shared output schema for both Local and Remote MCP tools."""

    output: str
    content: list[Any] = Field(default_factory=list, description="Raw MCP content items.")
    is_error: bool = Field(default=False, description="Whether the MCP server marked the call as an error.")


def process_mcp_result(result) -> tuple[str, list[Any], bool]:
    """
    Process MCP call_tool result into standard output format.

    Args:
        result: MCP SDK call_tool result object

    Returns:
        tuple: (output_string, content_items, is_error)
    """
    content_items = list(getattr(result, "content", []) or [])
    content_parts = [item.text for item in content_items if getattr(item, "text", None) is not None]
    is_error = bool(getattr(result, "isError", False))

    if content_parts:
        output = "\n".join(content_parts)
    elif is_error:
        output = json.dumps({"result": "error", "message": "MCP tool call failed with no output."})
    else:
        output = json.dumps({"result": "success"})

    return output, content_items, is_error


def convert_tool_to_description(tool) -> ToolDescription | None:
    """
    Convert MCP tool object to ToolDescription.

    Args:
        tool: MCP SDK tool object from list_tools result

    Returns:
        ToolDescription or None if tool has no name
    """
    input_schema = getattr(tool, "inputSchema", {}) or {}
    if not isinstance(input_schema, dict):
        input_schema = {}

    properties = input_schema.get("properties") or {}
    required = input_schema.get("required") or []
    name = getattr(tool, "name", None)

    if not name:
        return None

    return ToolDescription(
        name=name,
        description=getattr(tool, "description", None) or "",
        tool_properties=properties,
        required_tool_properties=required if isinstance(required, list) else [],
    )


async def execute_mcp_tool_call(
    inputs: MCPToolInputs,
    tool_description_map: dict[str, ToolDescription],
    call_tool_fn: Callable[[str, dict[str, Any]], Any],
    tool_type_name: str,
    trace_span_kind: str,
) -> MCPToolOutputs:
    """
    Execute an MCP tool call with validation, tracing, and result processing.

    Shared implementation for both LocalMCPTool and RemoteMCPTool to avoid code duplication.

    Args:
        inputs: Tool call inputs (name and arguments)
        tool_description_map: Map of tool names to their descriptions
        call_tool_fn: Async function that performs the actual tool call
        tool_type_name: "local" or "remote" for error messages
        trace_span_kind: OpenInference span kind for tracing

    Returns:
        MCPToolOutputs with the tool call result
    """
    tool_name = inputs.tool_name
    if not tool_name:
        raise ValueError(f"tool_name is required to call a {tool_type_name} MCP tool.")

    if tool_name not in tool_description_map:
        raise ValueError(f"Tool {tool_name} not found in MCP registry.")

    # TODO: Remove this after function-calling refactor
    arguments = inputs.tool_arguments.copy()
    if inputs.model_extra:
        arguments.update(inputs.model_extra)

    span = get_current_span()
    span.set_attributes({
        SpanAttributes.OPENINFERENCE_SPAN_KIND: trace_span_kind,
        SpanAttributes.TOOL_NAME: tool_name,
        SpanAttributes.TOOL_PARAMETERS: json.dumps(arguments),
    })
    result = await call_tool_fn(tool_name, arguments)

    output, content_items, is_error = process_mcp_result(result)

    return MCPToolOutputs(
        output=output,
        content=content_items,
        is_error=is_error,
    )
