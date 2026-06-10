"""Webhook setup tools."""

from uuid import UUID

from fastmcp import FastMCP

from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

DEVELOPER_ROLES = ("developer", "admin", "super_admin")

SPECS: list[ToolSpec] = [
    ToolSpec(
        name="create_typeform_webhook",
        description=(
            "Create or reuse a Typeform webhook for a project and return the callback URL plus signing secret. "
            "Requires developer role. If the webhook already exists, signing_secret is only returned when "
            "rotate_secret is true."
        ),
        method="post",
        path="/projects/{project_id}/webhooks/typeform",
        scope="role",
        roles=DEVELOPER_ROLES,
        path_params=(
            Param("project_id", UUID, description="Project ID from list_projects or get_project_overview."),
        ),
        body_fields=(
            Param("events", dict, default=None, description="Optional Typeform event filter metadata."),
            Param("filter_options", dict, default=None, description="Optional Draft'n Run trigger filter options."),
            Param("rotate_secret", bool, default=False, description="Generate and return a new signing secret."),
        ),
        return_annotation=dict,
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
