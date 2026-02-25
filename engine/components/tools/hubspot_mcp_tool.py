"""
HubSpot MCP Tool - Exposes tools from shinzo-labs/hubspot-mcp via stdio.

Subclasses LocalMCPTool with a dedicated `from_access_token` constructor that
loads tool descriptions from a frozen JSON schema instead of doing MCP discovery
at init time. This eliminates the ~10-20s npx startup overhead on every graph save.
"""

import json
from pathlib import Path
from typing import Self

from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager

_SCHEMA_PATH = Path(__file__).parent / "hubspot_mcp_schema.json"

_DEFAULT_TOOLS = [
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
]


class HubSpotMCPTool(LocalMCPTool):
    """Expose tools from shinzo-labs/hubspot-mcp via stdio (npx subprocess).

    Tool descriptions are loaded from a frozen local schema instead of being
    discovered via MCP at init time. To refresh the schema, run the discovery
    script and replace hubspot_mcp_schema.json.
    """

    @classmethod
    def from_access_token(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: str,
        allowed_tools: list[str] | None = None,
        timeout: int = 30,
    ) -> Self:
        if not access_token:
            raise ValueError("access_token is required")

        allowed = set(allowed_tools) if allowed_tools is not None else set(_DEFAULT_TOOLS)
        raw: list[dict] = json.loads(_SCHEMA_PATH.read_text())
        tool_descriptions = [
            ToolDescription(
                name=entry["name"],
                description=entry.get("description", ""),
                tool_properties=entry.get("properties", {}),
                required_tool_properties=entry.get("required", []),
            )
            for entry in raw
            if entry.get("name") in allowed
        ]

        return cls(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            command="npx",
            args=["-y", "@shinzolabs/hubspot-mcp"],
            env={
                "HUBSPOT_ACCESS_TOKEN": access_token,
                "TELEMETRY_ENABLED": "false",
                "PORT": "0",
            },
            timeout=timeout,
            tool_descriptions=tool_descriptions,
        )
