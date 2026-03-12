"""
HubSpot MCP Tool — wraps the internal FastMCP server via stdio.
"""

import sys
from typing import Self

from engine.components.tools.hubspot_mcp.server import get_tool_descriptions
from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager

_DEFAULT_TOOLS = {
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
}


class HubSpotMCPTool(LocalMCPTool):
    """Expose tools from the internal HubSpot FastMCP server via stdio subprocess."""

    @classmethod
    def from_access_token(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: str | None = None,
        allowed_tools: set[str] | None = None,
        timeout: int = 30,
    ) -> Self:
        if not access_token:
            raise ValueError(
                "HubSpot MCP requires a configured OAuth connection. "
                "Please select a HubSpot connection in the component settings."
            )

        allowed = allowed_tools if allowed_tools is not None else _DEFAULT_TOOLS
        tool_descriptions = get_tool_descriptions(allowed)

        return cls(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            command=sys.executable,
            args=["-m", "engine.components.tools.hubspot_mcp.server"],
            env={"HUBSPOT_ACCESS_TOKEN": access_token},
            timeout=timeout,
            tool_descriptions=tool_descriptions,
        )
