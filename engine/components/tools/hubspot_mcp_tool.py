"""
HubSpot MCP Tool — wraps the internal FastMCP server via stdio.
"""

import sys
from collections.abc import Collection
from typing import Optional, Self

from engine.components.tools.hubspot_mcp.server import get_tool_descriptions
from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs, MCPToolOutputs
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager

HUBSPOT_DEFAULT_TOOL_NAMES: tuple[str, ...] = (
    "auth_get_current_user",
    "crm_create_contact",
    "crm_update_contact",
    "crm_search_contacts",
    "crm_get_contact",
    "crm_create_company",
    "crm_update_company",
    "crm_search_companies",
    "crm_get_company",
    "crm_create_association",
    "crm_list_association_types",
    "notes_create",
    "emails_create",
    "tasks_create",
)


def _normalize_allowed_tools(allowed_tools: Collection[str] | None) -> set[str]:
    if allowed_tools is None:
        return set(HUBSPOT_DEFAULT_TOOL_NAMES)

    allowed = set(allowed_tools)
    unknown = allowed - set(HUBSPOT_DEFAULT_TOOL_NAMES)
    if unknown:
        raise ValueError(f"Unknown HubSpot tools: {sorted(unknown)}")
    return allowed


class HubSpotMCPTool(LocalMCPTool):
    """Expose tools from the internal HubSpot FastMCP server via stdio subprocess."""

    @classmethod
    async def from_access_token(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: str,
        allowed_tools: Collection[str] | None = None,
        timeout: int = 30,
    ) -> Self:
        if not access_token:
            raise ValueError("access_token is required")

        allowed = _normalize_allowed_tools(allowed_tools)
        tool_descriptions = await get_tool_descriptions(allowed)

        return cls(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            command=sys.executable,
            args=["-m", "engine.components.tools.hubspot_mcp.server"],
            env={"HUBSPOT_ACCESS_TOKEN": access_token} if access_token else None,
            timeout=timeout,
            tool_descriptions=tool_descriptions,
        )

    async def _run_without_io_trace(
        self,
        inputs: MCPToolInputs,
        ctx: Optional[dict],
    ) -> MCPToolOutputs:
        if not self.env or not self.env.get("HUBSPOT_ACCESS_TOKEN"):
            raise ValueError(
                "HubSpot MCP requires a configured OAuth connection. "
                "Please select a HubSpot connection in the component settings."
            )
        return await super()._run_without_io_trace(inputs, ctx)
