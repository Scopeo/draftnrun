"""Alert email management tools — configure per-project run failure email recipients."""

from uuid import UUID

from fastmcp import FastMCP

from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

_PROJECT_ID = Param("project_id", UUID, description="The project ID (from list_projects or get_project_overview).")
_ALERT_EMAIL_ID = Param("alert_email_id", UUID, description="The alert email ID to delete (from list_alert_emails).")
_EMAIL = Param("email", str, description="Email address to receive run failure alerts.")

SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_alert_emails",
        description=(
            "List email addresses configured to receive run failure alerts for a project. "
            "Alerts fire when a webhook- or cron-triggered run fails."
        ),
        method="get",
        path="/projects/{project_id}/alert-emails",
        path_params=(_PROJECT_ID,),
        return_annotation=list,
    ),
    # Note: these are project-scoped, so the role is enforced by the backend in the
    # project's own organization. An MCP-level scope="role" gate would check the
    # session's active org instead, which may differ from the project's org.
    ToolSpec(
        name="create_alert_email",
        description=(
            "Add an email address to receive run failure alerts for a project. "
            "Alerts are sent via Resend when a webhook- or cron-triggered run fails. "
            "Duplicate emails are rejected (409). "
            "The backend requires developer role or above in the project's organization."
        ),
        method="post",
        path="/projects/{project_id}/alert-emails",
        path_params=(_PROJECT_ID,),
        body_fields=(_EMAIL,),
    ),
    ToolSpec(
        name="delete_alert_email",
        description=(
            "Remove an email address from a project's run failure alert recipients. "
            "The backend requires developer role or above in the project's organization."
        ),
        method="delete",
        path="/projects/{project_id}/alert-emails/{alert_email_id}",
        path_params=(_PROJECT_ID, _ALERT_EMAIL_ID),
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
