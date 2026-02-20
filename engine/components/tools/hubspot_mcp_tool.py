"""
HubSpot MCP Tool - Exposes tools from shinzo-labs/hubspot-mcp via stdio.

Subclasses LocalMCPTool with a dedicated `from_access_token` constructor that
injects the OAuth token as HUBSPOT_ACCESS_TOKEN for the npx subprocess.
"""

from typing import Self

from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager

DEFAULT_HUBSPOT_MCP_TOOL_DESCRIPTION = ToolDescription(
    name="hubspot_mcp_tool",
    description="HubSpot MCP tool description. Please, ignore this. MCP tools are fetched from the server.",
    tool_properties={},
    required_tool_properties=[],
)


class HubSpotMCPTool(LocalMCPTool):
    """Expose tools from shinzo-labs/hubspot-mcp via stdio (npx subprocess)."""

    @classmethod
    async def from_access_token(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: str,
        timeout: int = 30,
    ) -> Self:
        if not access_token:
            raise ValueError("access_token is required")
        return await cls.from_mcp_server(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            command="npx",
            args=["-y", "@shinzolabs/hubspot-mcp"],
            env={
                "HUBSPOT_ACCESS_TOKEN": access_token,
                "TELEMETRY_ENABLED": "false",
            },
            timeout=timeout,
        )
