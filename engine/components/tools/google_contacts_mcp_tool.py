"""
Google Contacts MCP Tool - wraps the internal FastMCP server via stdio.
"""

import sys
from typing import Optional, Self

from pydantic import SecretStr

from engine.components.tools.google_contacts_mcp.server import get_tool_descriptions
from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs, MCPToolOutputs
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager

_DEFAULT_TOOLS = {
    "contacts_list_contacts",
    "contacts_get_contact",
}


class GoogleContactsMCPTool(LocalMCPTool):
    """Expose read-only tools from the internal Google Contacts FastMCP server via stdio subprocess."""

    @classmethod
    async def from_access_token(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: Optional[SecretStr] = None,
        allowed_tools: set[str] | None = None,
        timeout: int = 30,
    ) -> Self:
        allowed = allowed_tools if allowed_tools is not None else _DEFAULT_TOOLS
        tool_descriptions = await get_tool_descriptions(allowed)

        env = (
            {"GOOGLE_CONTACTS_ACCESS_TOKEN": access_token.get_secret_value()} if access_token is not None else None
        )

        return cls(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            command=sys.executable,
            args=["-m", "engine.components.tools.google_contacts_mcp.server"],
            env=env,
            timeout=timeout,
            tool_descriptions=tool_descriptions,
        )

    async def _run_without_io_trace(
        self,
        inputs: MCPToolInputs,
        ctx: Optional[dict],
    ) -> MCPToolOutputs:
        if not self.env or not self.env.get("GOOGLE_CONTACTS_ACCESS_TOKEN"):
            raise ValueError(
                "Google Contacts MCP requires a configured OAuth connection. "
                "Please select a Google Contacts connection in the component settings."
            )
        return await super()._run_without_io_trace(inputs, ctx)
