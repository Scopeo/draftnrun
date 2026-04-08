"""Project management tools."""

from typing import Annotated, Literal, Optional
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field

from mcp_server.client import api
from mcp_server.context import require_org_context, require_role
from mcp_server.tools._defaults import generate_entity_defaults
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

PROXY_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_project",
        description=(
            "Get details of a specific project by ID. "
            "Prefer get_project_overview for a richer view with draft/production versions and recent runs."
        ),
        method="get",
        path="/projects/{project_id}",
        path_params=(
            Param(
                "project_id",
                UUID,
                description="The project ID (from list_projects or get_project_overview).",
            ),
        ),
    ),
    ToolSpec(
        name="delete_project",
        description=(
            "Delete a project.\n\n"
            "Destructive operation — confirm user intent first. "
            "The backend enforces developer role or above."
        ),
        method="delete",
        path="/projects/{project_id}",
        path_params=(
            Param(
                "project_id",
                UUID,
                description="The project ID (from list_projects or get_project_overview).",
            ),
        ),
    ),
    ToolSpec(
        name="list_templates",
        description="List available project templates in the active organization.",
        method="get",
        path="/templates/{org_id}",
        scope="org",
        return_annotation=list,
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, PROXY_SPECS)

    @mcp.tool()
    async def list_projects(
        project_type: Annotated[
            Literal["WORKFLOW", "AGENT"],
            Field(description="Filter by type."),
        ] = "WORKFLOW",
        include_templates: Annotated[
            bool,
            Field(
                description=("Include template projects (may include cross-org templates)."),
            ),
        ] = False,
    ) -> list[dict]:
        """List all projects in the active organization.

        ⚠️ When ``include_templates`` is True, the response includes global
        template projects from **other organizations** (e.g. the platform
        Templates org).  Filter results by ``organization_id`` if you only
        want projects belonging to the active org.
        """
        jwt, user_id = _get_auth()
        org = await require_org_context(user_id)
        return await api.get(
            f"/projects/org/{org['org_id']}",
            jwt,
            type=project_type.lower(),
            include_templates=str(include_templates).lower(),
        )

    @mcp.tool()
    async def create_workflow(
        name: Annotated[str, Field(description="Project name.")],
        description: Annotated[str, Field(description="Optional description.")] = "",
    ) -> dict:
        """Create a new workflow project in the active organization.

        Creates a **workflow** — a multi-step DAG with a Start node, custom
        input fields, and multiple components.  If the user only needs a
        single AI agent with optional tools, use `create_agent` instead.

        Auto-generates a unique ID, icon, and color.  Requires active org
        context — call `select_organization` first.

        Authorization: caller must have one of the roles ``developer``,
        ``admin``, or ``super_admin``.  Raises if not authorized.
        """
        name = name.strip()
        if not name:
            raise ValueError("name must not be empty")

        jwt, user_id = _get_auth()
        org = await require_role(user_id, "developer", "admin", "super_admin")
        defaults = generate_entity_defaults()
        return await api.post(
            f"/projects/{org['org_id']}",
            jwt,
            json={
                "project_id": defaults["id"],
                "project_name": name,
                "description": description,
                "icon": defaults["icon"],
                "icon_color": defaults["icon_color"],
            },
        )

    @mcp.tool()
    async def update_project(
        project_id: Annotated[
            UUID,
            Field(
                description=("The project to update (from list_projects or get_project_overview)."),
            ),
        ],
        name: Annotated[Optional[str], Field(description="New name.")] = None,
        description: Annotated[Optional[str], Field(description="New description.")] = None,
    ) -> dict:
        """Update a project's name or description."""
        jwt, _ = _get_auth()
        body = {}
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("name must not be empty")
            body["name"] = name
        if description is not None:
            body["description"] = description
        if not body:
            raise ValueError("At least one field must be provided")
        return await api.patch(f"/projects/{project_id}", jwt, json=body)

    @mcp.tool()
    async def get_project_overview(
        project_id: Annotated[
            UUID,
            Field(
                description=("The project ID (from list_projects or create_workflow/create_agent)."),
            ),
        ],
    ) -> dict:
        """Get a comprehensive overview of a project in a single call.

        Returns the project details, identifies the editable draft and current
        production versions, includes the 5 most recent runs, and surfaces
        versioning safety hints. Use this before editing graphs, configuring
        agents, publishing, scheduling, or reasoning about live behavior.
        """
        jwt, _ = _get_auth()
        project = await api.get(f"/projects/{project_id}", jwt)

        graph_runners = project.get("graph_runners", [])
        draft = None
        production = None
        for gr in graph_runners:
            if gr.get("env") == "draft" and gr.get("tag_name") is None:
                draft = gr
            elif gr.get("env") == "production":
                production = gr

        draft_graph_runner_id = None
        if draft:
            draft_graph_runner_id = draft.get("graph_runner_id") or draft.get("id")

        production_graph_runner_id = None
        if production:
            production_graph_runner_id = production.get("graph_runner_id") or production.get("id")

        has_production_deployment = production is not None
        production_only_capabilities = {
            "cron_jobs": has_production_deployment,
            "widgets": has_production_deployment,
            "event_triggers": has_production_deployment,
        }

        warnings = [
            "Only the true draft runner (env='draft' and untagged) is editable.",
        ]
        if not draft_graph_runner_id:
            warnings.append(
                "No editable draft runner detected. Inspect graph history or publish flow carefully before editing."
            )
        if not has_production_deployment:
            warnings.append(
                "No production deployment found. Cron jobs, widgets, "
                "and event-trigger flows should not be treated as live."
            )

        safe_next_steps = []
        if draft_graph_runner_id:
            safe_next_steps.append(
                f"Use get_graph('{project_id}', '{draft_graph_runner_id}') before any update_graph call."
            )
            safe_next_steps.append(
                f"Use save_graph_version('{project_id}', '{draft_graph_runner_id}') "
                "before publish_to_production when you want a reusable snapshot."
            )
        else:
            safe_next_steps.append("No editable draft detected; inspect graph history before attempting edits.")

        if has_production_deployment:
            safe_next_steps.append(
                f"Use production runner '{production_graph_runner_id}' only when reasoning about live behavior."
            )
        else:
            safe_next_steps.append("Publish a version before configuring cron jobs, widgets, or event-trigger flows.")

        recent_runs = await api.get(f"/projects/{project_id}/runs", jwt, page=1, page_size=5)

        return {
            "project": {
                "id": project.get("id") or project.get("project_id"),
                "name": project.get("name") or project.get("project_name"),
                "description": project.get("description"),
                "type": project.get("type") or project.get("project_type"),
            },
            "draft_version": draft,
            "production_version": production,
            "editable_draft_graph_runner_id": draft_graph_runner_id,
            "production_graph_runner_id": production_graph_runner_id,
            "has_production_deployment": has_production_deployment,
            "production_only_capabilities": production_only_capabilities,
            "warnings": warnings,
            "safe_next_steps": safe_next_steps,
            "all_versions_count": len(graph_runners),
            "recent_runs": recent_runs,
        }
