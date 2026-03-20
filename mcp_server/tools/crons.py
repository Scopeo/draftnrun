"""Cron job management tools."""

from fastmcp import FastMCP

from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

_BASE = "/organizations/{org_id}/crons"
_ITEM = f"{_BASE}/{{cron_id}}"
_CRON_ID = Param("cron_id", str, description="The cron job ID.")

SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_crons",
        description=(
            "List all cron jobs in the active organization.\n\n"
            "Cron jobs are organization-scoped in MCP. The frontend treats schedule "
            "and event-trigger flows as production-oriented behavior."
        ),
        method="get",
        path=_BASE,
        scope="org",
        return_annotation=list,
    ),
    ToolSpec(
        name="get_cron",
        description="Get details of a specific cron job.",
        method="get",
        path=_ITEM,
        scope="org",
        path_params=(_CRON_ID,),
    ),
    ToolSpec(
        name="create_cron",
        description=(
            "Create a new cron job. Requires developer role.\n\n"
            "Runtime note: successful CRUD writes DB state first; scheduler pickup "
            "can lag slightly behind the API response."
        ),
        method="post",
        path=_BASE,
        scope="role",
        roles=("developer", "admin", "super_admin"),
        body_param=Param(
            "cron_data",
            dict,
            description=(
                "Cron configuration. Required fields: name (str), cron_expr (str), "
                "tz (str), entrypoint ('agent_inference' or 'endpoint_polling'), payload (dict). "
                "For cron_expr, use textual weekday names in ranges (e.g. '0 9 * * mon-fri', "
                "not '0 9 * * 1-5')."
            ),
        ),
    ),
    ToolSpec(
        name="update_cron",
        description="Update a cron job. Requires developer role.",
        method="patch",
        path=_ITEM,
        scope="role",
        roles=("developer", "admin", "super_admin"),
        path_params=(_CRON_ID,),
        body_param=Param(
            "cron_data", dict,
            description="Updated cron fields. Use `payload`, not `input_data`, at the top level.",
        ),
    ),
    ToolSpec(
        name="delete_cron",
        description="Delete a cron job. Requires developer role.",
        method="delete",
        path=_ITEM,
        scope="role",
        roles=("developer", "admin", "super_admin"),
        path_params=(_CRON_ID,),
    ),
    ToolSpec(
        name="pause_cron",
        description="Pause a running cron job. Requires developer role.",
        method="post",
        path=f"{_ITEM}/pause",
        scope="role",
        roles=("developer", "admin", "super_admin"),
        path_params=(_CRON_ID,),
    ),
    ToolSpec(
        name="resume_cron",
        description="Resume a paused cron job. Requires developer role.",
        method="post",
        path=f"{_ITEM}/resume",
        scope="role",
        roles=("developer", "admin", "super_admin"),
        path_params=(_CRON_ID,),
    ),
    ToolSpec(
        name="get_cron_runs",
        description="Get execution history for a cron job.",
        method="get",
        path=f"{_ITEM}/runs",
        scope="org",
        path_params=(_CRON_ID,),
        return_annotation=list,
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
