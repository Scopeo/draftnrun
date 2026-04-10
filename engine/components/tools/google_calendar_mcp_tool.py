"""
Google Calendar MCP Tool — wraps the internal FastMCP server via stdio.
"""

import sys
from typing import Optional, Self

from engine.components.tools.google_calendar_mcp.server import get_tool_descriptions
from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs, MCPToolOutputs
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager

_DEFAULT_TOOLS = {
    "calendar_list_calendars",
    "calendar_list_events",
    "calendar_get_event",
    "calendar_get_my_email",
    "calendar_create_event",
    "calendar_update_event",
    "calendar_delete_event",
}


class GoogleCalendarMCPTool(LocalMCPTool):
    """Expose tools from the internal Google Calendar FastMCP server via stdio subprocess."""

    @classmethod
    async def from_access_token(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: Optional[str] = None,
        allowed_tools: set[str] | None = None,
        timeout: int = 30,
    ) -> Self:
        allowed = allowed_tools if allowed_tools is not None else _DEFAULT_TOOLS
        tool_descriptions = await get_tool_descriptions(allowed)

        return cls(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            command=sys.executable,
            args=["-m", "engine.components.tools.google_calendar_mcp.server"],
            env={"GOOGLE_CALENDAR_ACCESS_TOKEN": access_token} if access_token else None,
            timeout=timeout,
            tool_descriptions=tool_descriptions,
        )

    async def _run_without_io_trace(
        self,
        inputs: MCPToolInputs,
        ctx: Optional[dict],
    ) -> MCPToolOutputs:
        if not self.env or not self.env.get("GOOGLE_CALENDAR_ACCESS_TOKEN"):
            raise ValueError(
                "Google Calendar MCP requires a configured OAuth connection. "
                "Please select a Google Calendar connection in the component settings."
            )
        return await super()._run_without_io_trace(inputs, ctx)
