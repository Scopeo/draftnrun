"""
Notion MCP Tool — wraps the internal FastMCP server via stdio.
"""

import sys
from collections.abc import Collection
from typing import Optional, Self

from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs, MCPToolOutputs
from engine.components.tools.notion_mcp.server import get_tool_descriptions
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager

NOTION_DEFAULT_TOOL_NAMES: tuple[str, ...] = (
    "search",
    "get_self",
    "get_database",
    "create_database",
    "update_database",
    "query_database",
    "create_page",
    "update_page",
    "get_page",
    "append_blocks",
    "get_block_children",
    "delete_block",
    "set_icon",
    "list_views",
    "create_view",
    "upsert_page_by_property",
    "replace_page_blocks",
)


def _normalize_allowed_tools(allowed_tools: Collection[str] | None) -> set[str]:
    if allowed_tools is None:
        return set(NOTION_DEFAULT_TOOL_NAMES)

    allowed = set(allowed_tools)
    unknown = allowed - set(NOTION_DEFAULT_TOOL_NAMES)
    if unknown:
        raise ValueError(f"Unknown Notion tools: {sorted(unknown)}")
    return allowed


class NotionMCPTool(LocalMCPTool):
    """Expose tools from the internal Notion FastMCP server via stdio subprocess."""

    @classmethod
    async def from_access_token(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: str,
        allowed_tools: Collection[str] | None = None,
        timeout: int = 30,
    ) -> Self:
        allowed = _normalize_allowed_tools(allowed_tools)
        tool_descriptions = await get_tool_descriptions(allowed)

        return cls(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            command=sys.executable,
            args=["-m", "engine.components.tools.notion_mcp.server"],
            env={"NOTION_ACCESS_TOKEN": access_token} if access_token else None,
            timeout=timeout,
            tool_descriptions=tool_descriptions,
        )

    def is_available(self) -> bool:
        return bool(self.env and self.env.get("NOTION_ACCESS_TOKEN"))

    async def _run_without_io_trace(
        self,
        inputs: MCPToolInputs,
        ctx: Optional[dict],
    ) -> MCPToolOutputs:
        if not self.env or not self.env.get("NOTION_ACCESS_TOKEN"):
            raise ValueError(
                "Notion MCP requires a configured OAuth connection. "
                "Please select a Notion connection in the component settings."
            )
        return await super()._run_without_io_trace(inputs, ctx)
