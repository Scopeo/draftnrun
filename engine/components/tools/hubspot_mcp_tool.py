"""
HubSpot MCP Tool — wraps the internal FastMCP server via stdio.
"""

import sys
from typing import Optional, Type

from pydantic import BaseModel, Field

from ada_backend.database.models import UIComponent, UIComponentProperties
from ada_backend.services.integration_service import resolve_oauth_access_token
from engine.components.tools.hubspot_mcp.server import get_tool_descriptions
from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs, MCPToolOutputs
from engine.components.types import ComponentAttributes
from engine.integrations.providers import OAuthProvider
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


class HubSpotMCPToolInputs(MCPToolInputs):
    oauth_connection_id: str = Field(
        description="OAuth connection for HubSpot",
        json_schema_extra={
            "is_tool_input": False,
            "ui_component": UIComponent.OAUTH_CONNECTION,
            "ui_component_properties": UIComponentProperties(
                label="HubSpot Connection",
                description="Select your authorized HubSpot account connection",
                provider=OAuthProvider.HUBSPOT.value,
                icon="logos:hubspot",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )


class HubSpotNeverdropMCPToolInputs(MCPToolInputs):
    oauth_connection_id: str = Field(
        description="OAuth connection for HubSpot Neverdrop",
        json_schema_extra={
            "is_tool_input": False,
            "ui_component": UIComponent.OAUTH_CONNECTION,
            "ui_component_properties": UIComponentProperties(
                label="HubSpot Neverdrop Connection",
                description="Select your authorized HubSpot Neverdrop account connection",
                provider=OAuthProvider.HUBSPOT_NEVERDROP.value,
                icon="logos:hubspot",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )


class HubSpotMCPTool(LocalMCPTool):
    """Expose tools from the internal HubSpot FastMCP server via stdio subprocess."""

    _OAUTH_PROVIDER = OAuthProvider.HUBSPOT

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        allowed_tools: set[str] | None = None,
        timeout: int = 30,
    ):
        allowed = allowed_tools if allowed_tools is not None else _DEFAULT_TOOLS
        tool_descriptions = get_tool_descriptions(allowed)

        super().__init__(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            command=sys.executable,
            args=["-m", "engine.components.tools.hubspot_mcp.server"],
            env=None,
            timeout=timeout,
            tool_descriptions=tool_descriptions,
        )

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return HubSpotMCPToolInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return MCPToolOutputs

    async def _run_without_io_trace(
        self,
        inputs: HubSpotMCPToolInputs,
        ctx: Optional[dict],
    ) -> MCPToolOutputs:
        access_token = await resolve_oauth_access_token(
            definition_id=inputs.oauth_connection_id,
            provider_config_key=self._OAUTH_PROVIDER.value,
        )
        self.env = {"HUBSPOT_ACCESS_TOKEN": access_token}
        return await super()._run_without_io_trace(inputs, ctx)
