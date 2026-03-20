"""OAuth connections management tools.

Only read and revoke operations are exposed. The OAuth authorization flow
requires a browser and must be completed in the web UI with explicit user
permission.
"""

from fastmcp import FastMCP

from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

_BASE = "/organizations/{org_id}/oauth-connections"

SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_oauth_connections",
        description="List OAuth connections for the active organization. Requires developer role.",
        method="get",
        path=_BASE,
        scope="role",
        roles=("developer", "admin", "super_admin"),
        query_params=(
            Param(
                "provider_config_key", str, default=None,
                description="Optional provider filter (e.g. 'google-mail', 'slack').",
            ),
        ),
        return_annotation=list,
    ),
    ToolSpec(
        name="check_oauth_status",
        description="Check the status of a specific OAuth connection. Requires developer role.",
        method="get",
        path=f"{_BASE}/status",
        scope="role",
        roles=("developer", "admin", "super_admin"),
        query_params=(
            Param("provider_config_key", str, description="Provider key (e.g. 'google-mail', 'slack')."),
            Param("connection_id", str, description="The OAuth connection ID to check."),
        ),
    ),
    ToolSpec(
        name="revoke_oauth",
        description=(
            "Revoke an OAuth connection.\n\n"
            "Destructive operation: confirm user intent before calling. Requires developer role."
        ),
        method="delete",
        path=f"{_BASE}/{{connection_id}}",
        scope="role",
        roles=("developer", "admin", "super_admin"),
        path_params=(Param("connection_id", str, description="The connection ID."),),
        query_params=(Param("provider_config_key", str, description="Provider key (e.g. 'google-mail', 'slack')."),),
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
