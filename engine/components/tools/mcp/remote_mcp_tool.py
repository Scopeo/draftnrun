import logging
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.sse import sse_client
from openinference.semconv.trace import OpenInferenceSpanKindValues

from engine.components.component import Component
from engine.components.errors import MCPConnectionError
from engine.components.tools.mcp.shared import (
    DEFAULT_MCP_TOOL_DESCRIPTION,
    MCPToolInputs,
    MCPToolOutputs,
    convert_tool_to_description,
    execute_mcp_tool_call,
)
from engine.components.types import ComponentAttributes, ToolDescription
from engine.components.utils import load_str_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


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
                self._mcp_tool_descriptions[0] if self._mcp_tool_descriptions else DEFAULT_MCP_TOOL_DESCRIPTION
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
            raise MCPConnectionError(temp.server_url, str(exc)) from exc
        tools = list(getattr(tools_result, "tools", []) or [])

        tool_descriptions: list[ToolDescription] = []
        for tool in tools:
            description = convert_tool_to_description(tool)
            if description:
                tool_descriptions.append(description)

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
        return MCPToolInputs

    @classmethod
    def get_outputs_schema(cls):
        return MCPToolOutputs

    async def _run_without_io_trace(
        self,
        inputs: MCPToolInputs,
        ctx: Optional[dict],
    ) -> MCPToolOutputs:
        return await execute_mcp_tool_call(
            inputs=inputs,
            tool_description_map=self._tool_description_map,
            call_tool_fn=self._call_tool_with_sdk,
            tool_type_name="remote",
            trace_span_kind=self.TRACE_SPAN_KIND,
        )

    async def _call_tool_with_sdk(self, tool_name: str, arguments: dict[str, Any]):
        """Use MCP SDK to call a tool."""
        try:
            async with sse_client(self.server_url, headers=self.headers, timeout=self.timeout) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(tool_name, arguments=arguments)
        except Exception as exc:  # noqa: BLE001 - keep root cause attached
            raise MCPConnectionError(self.server_url, str(exc)) from exc
