"""Alert email management tools — configure per-project run failure email recipients."""

from uuid import UUID

from fastmcp import FastMCP

from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

_PROJECT_ID = Param(
    "project_id", UUID, description="The project ID (from list_projects or get_project_overview)."
)
_ALERT_EMAIL_ID = Param(
    "alert_email_id", UUID, description="The alert email ID to remove (from list_alert_emails)."
)
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
    ToolSpec(
        name="add_alert_email",
        description=(
            "Add an email address to receive run failure alerts for a project. "
            "Alerts are sent via Resend when a webhook- or cron-triggered run fails. "
            "Duplicate emails are rejected (409)."
        ),
        method="post",
        path="/projects/{project_id}/alert-emails",
        path_params=(_PROJECT_ID,),
        body_fields=(_EMAIL,),
    ),
    ToolSpec(
        name="remove_alert_email",
        description="Remove an email address from a project's run failure alert recipients.",
        method="delete",
        path="/projects/{project_id}/alert-emails/{alert_email_id}",
        path_params=(_PROJECT_ID, _ALERT_EMAIL_ID),
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
