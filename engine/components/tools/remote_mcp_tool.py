import json
import logging
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.sse import sse_client
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from engine.components.component import Component
from engine.components.errors import RemoteMCPConnectionError
from engine.components.types import ComponentAttributes, ToolDescription
from engine.components.utils import load_str_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

DEFAULT_REMOTE_MCP_TOOL_DESCRIPTION = ToolDescription(
    name="remote_mcp_tool",
    description="Remote MCP tool description. Please, ignore this. MCP tools are fetched from the server.",
    tool_properties={},
    required_tool_properties=[],
)


class RemoteMCPToolInputs(BaseModel):
    tool_name: str = Field(description="Name of the MCP tool to call.", json_schema_extra={"disabled_as_input": True})
    tool_arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to pass to the MCP tool.",
        json_schema_extra={"disabled_as_input": True},
    )
    # TODO: Remove this after function-calling refactor
    model_config = {"extra": "allow"}


class RemoteMCPToolOutputs(BaseModel):
    output: str
    content: list[Any] = Field(default_factory=list, description="Raw MCP content items.")
    is_error: bool = Field(default=False, description="Whether the MCP server marked the call as an error.")


class RemoteMCPTool(Component):
    """Expose tools from a remote MCP server as individual tool calls."""

    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True
    # TODO: replace this flag-based wiring with a proper function-calling→input translation hook
    requires_tool_name = True

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        server_url: str,
        headers: Optional[dict[str, Any]] = None,
        timeout: int = 30,
        tool_descriptions: list[ToolDescription] | None = None,
    ):
        if not server_url:
            raise ValueError("server_url is required for RemoteMCPTool.")
        self.server_url = server_url.strip().rstrip("/")
        if isinstance(headers, str):
            self.headers = load_str_to_json(headers) if headers else {}
        else:
            self.headers = headers or {}
        self.timeout = timeout
        if tool_descriptions is None:
            raise ValueError("Provide tool_descriptions or use RemoteMCPTool.from_mcp_server for auto-discovery.")
        self._mcp_tool_descriptions = tool_descriptions
        self._tool_description_map = {td.name: td for td in self._mcp_tool_descriptions}

        super().__init__(
            trace_manager=trace_manager,
            tool_description=(
                self._mcp_tool_descriptions[0] if self._mcp_tool_descriptions else DEFAULT_REMOTE_MCP_TOOL_DESCRIPTION
            ),
            component_attributes=component_attributes,
        )

    def get_tool_descriptions(self) -> list[ToolDescription]:
        """Return all tool descriptions fetched from the MCP server."""
        return self._mcp_tool_descriptions

    async def _list_tools_with_sdk(self):
        """Use MCP SDK to list tools."""
        async with sse_client(self.server_url, headers=self.headers, timeout=self.timeout) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.list_tools()

    @classmethod
    async def from_mcp_server(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        server_url: str,
        headers: Optional[dict[str, Any]] = None,
        timeout: int = 30,
    ) -> "RemoteMCPTool":
        """Convenience async constructor that fetches tool descriptions via MCP SDK."""
        temp = cls.__new__(cls)
        if not server_url:
            raise ValueError("server_url is required for RemoteMCPTool.")
        temp.server_url = server_url.strip().rstrip("/")
        if isinstance(headers, str):
            temp.headers = load_str_to_json(headers) if headers else {}
        else:
            temp.headers = headers or {}
        temp.timeout = timeout
        try:
            tools_result = await temp._list_tools_with_sdk()
        except Exception as exc:  # noqa: BLE001 - surface readable error to the user
            raise RemoteMCPConnectionError(temp.server_url, str(exc)) from exc
        tools = list(getattr(tools_result, "tools", []) or [])

        tool_descriptions: list[ToolDescription] = []
        for tool in tools:
            input_schema = getattr(tool, "inputSchema", {}) or {}
            if not isinstance(input_schema, dict):
                input_schema = {}
            properties = input_schema.get("properties") or {}
            required = input_schema.get("required") or []
            name = getattr(tool, "name", None)
            if not name:
                continue
            tool_descriptions.append(
                ToolDescription(
                    name=name,
                    description=getattr(tool, "description", ""),
                    tool_properties=properties,
                    required_tool_properties=required if isinstance(required, list) else [],
                )
            )

        return cls(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            server_url=server_url,
            headers=headers,
            timeout=timeout,
            tool_descriptions=tool_descriptions,
        )

    @classmethod
    def get_inputs_schema(cls):
        return RemoteMCPToolInputs

    @classmethod
    def get_outputs_schema(cls):
        return RemoteMCPToolOutputs

    async def _run_without_io_trace(
        self,
        inputs: RemoteMCPToolInputs,
        ctx: Optional[dict],
    ) -> RemoteMCPToolOutputs:
        tool_name = inputs.tool_name
        if not tool_name:
            raise ValueError("tool_name is required to call a remote MCP tool.")

        if tool_name not in self._tool_description_map:
            raise ValueError(f"Tool {tool_name} not found in MCP registry.")

        # TODO: Remove this after function-calling refactor
        arguments = inputs.tool_arguments.copy()
        if inputs.model_extra:
            arguments.update(inputs.model_extra)

        span = get_current_span()
        span.set_attributes({
            SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
            SpanAttributes.TOOL_NAME: tool_name,
            SpanAttributes.TOOL_PARAMETERS: json.dumps(arguments),
        })
        result = await self._call_tool_with_sdk(tool_name=tool_name, arguments=arguments)

        content_items = list(getattr(result, "content", []) or [])
        content_parts = [item.text for item in content_items if getattr(item, "text", None) is not None]
        content = "\n".join(content_parts) if content_parts else json.dumps({"result": "success"})

        return RemoteMCPToolOutputs(
            output=content,
            content=content_items,
            is_error=bool(getattr(result, "isError", False)),
        )

    async def _call_tool_with_sdk(self, tool_name: str, arguments: dict[str, Any]):
        """Use MCP SDK to call a tool."""
        try:
            async with sse_client(self.server_url, headers=self.headers, timeout=self.timeout) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(tool_name, arguments=arguments)
        except Exception as exc:  # noqa: BLE001 - keep root cause attached
            raise RemoteMCPConnectionError(self.server_url, str(exc)) from exc
