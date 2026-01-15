"""
HubSpot MCP Tool - Connects to HubSpot's MCP server using Streamable HTTP transport.

This tool connects to https://mcp.hubspot.com/ using OAuth Bearer token authentication.
Unlike RemoteMCPTool which uses SSE transport, HubSpot requires Streamable HTTP.
# TODO: Quick and dirty implementation. Deduplicate with RemoteMCP
"""

import json
import logging
from typing import Any, Optional

import httpx
from mcp import ClientSession
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from engine.components.component import Component
from engine.components.errors import RemoteMCPConnectionError
from engine.components.tools.hubspot_streamable_http import streamable_http_client
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager
from settings import settings

LOGGER = logging.getLogger(__name__)

HUBSPOT_MCP_SERVER_URL = "https://mcp.hubspot.com/"

DEFAULT_HUBSPOT_MCP_TOOL_DESCRIPTION = ToolDescription(
    name="hubspot_mcp_tool",
    description="HubSpot MCP tool description. Please, ignore this. MCP tools are fetched from the server.",
    tool_properties={},
    required_tool_properties=[],
)


class HubSpotMCPToolInputs(BaseModel):
    tool_name: str = Field(description="Name of the MCP tool to call.", json_schema_extra={"disabled_as_input": True})
    tool_arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to pass to the MCP tool.",
        json_schema_extra={"disabled_as_input": True},
    )
    # TODO: Remove this after function-calling refactor
    model_config = {"extra": "allow"}


class HubSpotMCPToolOutputs(BaseModel):
    output: str
    content: list[Any] = Field(default_factory=list, description="Raw MCP content items.")
    is_error: bool = Field(default=False, description="Whether the MCP server marked the call as an error.")


class HubSpotMCPTool(Component):
    """Expose tools from HubSpot's MCP server using Streamable HTTP transport."""

    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True
    # TODO: replace this flag-based wiring with a proper function-calling→input translation hook
    requires_tool_name = True

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: Optional[str] = None,
        timeout: int = 30,
        tool_descriptions: list[ToolDescription] | None = None,
    ):
        self.server_url = HUBSPOT_MCP_SERVER_URL
        self.access_token = access_token or settings.HUBSPOT_MCP_ACCESS_TOKEN
        self.refresh_token = settings.HUBSPOT_MCP_REFRESH_TOKEN
        self.client_id = settings.HUBSPOT_MCP_CLIENT_ID
        self.client_secret = settings.HUBSPOT_MCP_CLIENT_SECRET
        if not (self.refresh_token and self.client_id and self.client_secret):
            raise ValueError(
                "HUBSPOT_MCP_REFRESH_TOKEN, HUBSPOT_MCP_CLIENT_ID, and HUBSPOT_MCP_CLIENT_SECRET are required."
            )
        self.timeout = timeout

        if tool_descriptions is None:
            raise ValueError("Provide tool_descriptions or use HubSpotMCPTool.from_mcp_server for auto-discovery.")
        self._mcp_tool_descriptions = tool_descriptions
        self._tool_description_map = {td.name: td for td in self._mcp_tool_descriptions}

        super().__init__(
            trace_manager=trace_manager,
            tool_description=(
                self._mcp_tool_descriptions[0] if self._mcp_tool_descriptions else DEFAULT_HUBSPOT_MCP_TOOL_DESCRIPTION
            ),
            component_attributes=component_attributes,
        )

    def get_tool_descriptions(self) -> list[ToolDescription]:
        """Return all tool descriptions fetched from the HubSpot MCP server."""
        return self._mcp_tool_descriptions

    def _get_headers(self) -> dict[str, str]:
        """Get headers with Bearer token for HubSpot MCP."""
        return {"Authorization": f"Bearer {self.access_token}"}

    def _create_http_client(self) -> httpx.AsyncClient:
        """Create httpx.AsyncClient configured with Bearer token for HubSpot MCP."""
        return httpx.AsyncClient(
            headers=self._get_headers(),
            timeout=httpx.Timeout(self.timeout, read=300.0),
        )

    async def _list_tools_with_sdk(self):
        """Use MCP SDK with Streamable HTTP to list tools from HubSpot MCP server."""
        await self._refresh_access_token()
        client = self._create_http_client()
        try:
            async with streamable_http_client(self.server_url, http_client=client, terminate_on_close=True) as (
                read,
                write,
                _get_session_id,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.list_tools()
        finally:
            await client.aclose()

    async def _refresh_access_token(self) -> None:
        token_url = "https://api.hubapi.com/oauth/v1/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            if not self.access_token:
                raise ValueError("Failed to get access_token from refresh response")
            if "refresh_token" in token_data:
                self.refresh_token = token_data["refresh_token"]

    @classmethod
    async def from_mcp_server(
        cls,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: Optional[str] = None,
        timeout: int = 30,
    ) -> "HubSpotMCPTool":
        """Convenience async constructor that fetches tool descriptions via MCP SDK."""
        temp = cls.__new__(cls)
        temp.server_url = HUBSPOT_MCP_SERVER_URL
        temp.access_token = access_token or settings.HUBSPOT_MCP_ACCESS_TOKEN
        temp.refresh_token = settings.HUBSPOT_MCP_REFRESH_TOKEN
        temp.client_id = settings.HUBSPOT_MCP_CLIENT_ID
        temp.client_secret = settings.HUBSPOT_MCP_CLIENT_SECRET
        temp.timeout = timeout
        if not (temp.refresh_token and temp.client_id and temp.client_secret):
            raise ValueError(
                "HUBSPOT_MCP_REFRESH_TOKEN, HUBSPOT_MCP_CLIENT_ID, and HUBSPOT_MCP_CLIENT_SECRET are required."
            )
        await temp._refresh_access_token()

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
            access_token=temp.access_token,
            timeout=timeout,
            tool_descriptions=tool_descriptions,
        )

    @classmethod
    def get_inputs_schema(cls):
        return HubSpotMCPToolInputs

    @classmethod
    def get_outputs_schema(cls):
        return HubSpotMCPToolOutputs

    async def _run_without_io_trace(  # type: ignore[override]
        self,
        inputs: HubSpotMCPToolInputs,  # type: ignore[assignment]
        ctx: dict[str, Any],
    ) -> HubSpotMCPToolOutputs:  # type: ignore[override]
        tool_name = inputs.tool_name  # type: ignore[attr-defined]
        if not tool_name:
            raise ValueError("tool_name is required to call a HubSpot MCP tool.")

        if tool_name not in self._tool_description_map:
            raise ValueError(f"Tool {tool_name} not found in HubSpot MCP registry.")

        # TODO: Remove this after function-calling refactor
        arguments = inputs.tool_arguments.copy()  # type: ignore[attr-defined]
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

        return HubSpotMCPToolOutputs(
            output=content,
            content=content_items,
            is_error=bool(getattr(result, "isError", False)),
        )

    async def _call_tool_with_sdk(self, tool_name: str, arguments: dict[str, Any]):
        """Use MCP SDK with Streamable HTTP to call a tool on HubSpot MCP server."""
        await self._refresh_access_token()
        client = self._create_http_client()
        try:
            async with streamable_http_client(self.server_url, http_client=client, terminate_on_close=True) as (
                read,
                write,
                _get_session_id,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await session.call_tool(tool_name, arguments=arguments)
        except Exception as exc:  # noqa: BLE001 - keep root cause attached
            raise RemoteMCPConnectionError(self.server_url, str(exc)) from exc
        finally:
            await client.aclose()
