"""Monitoring, traces, and credit usage tools."""

from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field

from mcp_server.client import api
from mcp_server.context import require_org_context
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

DEFAULT_DURATION_DAYS = 30
MIN_DURATION_DAYS = 1
MAX_DURATION_DAYS = 365

PROXY_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_trace_tree",
        description="Get the full span tree for a specific trace.",
        method="get",
        path="/traces/{trace_id}/tree",
        path_params=(Param("trace_id", UUID, description="The trace ID (from list_traces or run)."),),
    ),
    ToolSpec(
        name="get_credit_usage",
        description="Get credit usage breakdown for the active organization.",
        method="get",
        path="/organizations/{org_id}/credit-usage",
        scope="org",
    ),
]


def _normalize_duration(duration: int) -> int:
    if isinstance(duration, bool):
        raise ValueError("Duration must be an integer number of days between 1 and 365.")
    try:
        duration_int = int(duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("Duration must be an integer number of days between 1 and 365.") from exc
    return max(MIN_DURATION_DAYS, min(duration_int, MAX_DURATION_DAYS))


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, PROXY_SPECS)

    @mcp.tool()
    async def list_traces(
        project_id: Annotated[UUID, Field(description="The project ID (from list_projects or get_project_overview).")],
        page: Annotated[int, Field(description="Page number (1-based).")] = 1,
        page_size: Annotated[int, Field(description="Results per page (max 100).")] = 50,
    ) -> dict:
        """List execution traces for a project."""
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1:
            raise ValueError("page_size must be >= 1")

        jwt, _ = _get_auth()
        return await api.get(
            f"/projects/{project_id}/traces",
            jwt,
            page=page,
            page_size=min(page_size, 100),
        )

    @mcp.tool()
    async def get_org_charts(
        duration: Annotated[
            int,
            Field(description="Number of days to include. Clamped to 1-365."),
        ] = DEFAULT_DURATION_DAYS,
    ) -> dict:
        """Get organization-level monitoring charts."""
        duration = _normalize_duration(duration)
        jwt, user_id = _get_auth()
        org = await require_org_context(user_id)
        return await api.get(f"/monitor/org/{org['org_id']}/charts", jwt, duration=duration)

    @mcp.tool()
    async def get_org_kpis(
        duration: Annotated[
            int,
            Field(description="Number of days to include. Clamped to 1-365."),
        ] = DEFAULT_DURATION_DAYS,
    ) -> dict:
        """Get organization-level KPI metrics."""
        duration = _normalize_duration(duration)
        jwt, user_id = _get_auth()
        org = await require_org_context(user_id)
        return await api.get(f"/monitor/org/{org['org_id']}/kpis", jwt, duration=duration)
