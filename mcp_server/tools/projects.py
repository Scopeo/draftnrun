"""Project management tools."""

from typing import Optional

from fastmcp import FastMCP

from mcp_server.client import api
from mcp_server.context import require_org_context
from mcp_server.tools._defaults import generate_entity_defaults
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

PROXY_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_project",
        description="Get details of a specific project by ID.",
        method="get",
        path="/projects/{project_id}",
        path_params=(Param("project_id", str, description="The project ID."),),
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
        path_params=(Param("project_id", str, description="The project ID."),),
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
        project_type: str = "WORKFLOW",
        include_templates: bool = False,
    ) -> list[dict]:
        """List all projects in the active organization.

        Args:
            project_type: Filter by type (WORKFLOW or AGENT). Defaults to WORKFLOW.
            include_templates: Include template projects. Defaults to False.
        """
        _VALID_PROJECT_TYPES = {"WORKFLOW", "AGENT"}
        normalized = project_type.strip().upper()
        if normalized not in _VALID_PROJECT_TYPES:
            raise ValueError(f"project_type must be one of {sorted(_VALID_PROJECT_TYPES)}, got '{project_type}'")
        project_type = normalized

        jwt, user_id = _get_auth()
        org = await require_org_context(user_id)
        return await api.get(
            f"/projects/org/{org['org_id']}",
            jwt,
            type=project_type.lower(),
            include_templates=str(include_templates).lower(),
        )

    @mcp.tool()
    async def create_project(name: str, description: str = "") -> dict:
        """Create a new workflow project in the active organization.

        Always creates a **workflow** project. Agent projects are created via
        `create_agent` instead. Auto-generates a unique ID, icon, and color.

        Requires active org context — call `select_organization` first.

        Args:
            name: Project name.
            description: Optional description.
        """
        name = name.strip()
        if not name:
            raise ValueError("name must not be empty")

        jwt, user_id = _get_auth()
        org = await require_org_context(user_id)
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
    async def update_project(project_id: str, name: Optional[str] = None, description: Optional[str] = None) -> dict:
        """Update a project's name or description.

        Args:
            project_id: The project to update.
            name: New name (optional).
            description: New description (optional).
        """
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
            raise ValueError("name or description must be provided")
        return await api.patch(f"/projects/{project_id}", jwt, json=body)

    @mcp.tool()
    async def get_project_overview(project_id: str) -> dict:
        """Get a comprehensive overview of a project in a single call.

        Returns the project details, identifies the editable draft and current
        production versions, includes the 5 most recent runs, and surfaces
        versioning safety hints. Use this before editing graphs, configuring
        agents, publishing, scheduling, or reasoning about live behavior.

        Args:
            project_id: The project ID.
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
            safe_next_steps.append(
                "Publish a version before configuring cron jobs, widgets, or event-trigger flows."
            )

        recent_runs = await api.get(
            f"/projects/{project_id}/runs", jwt, page=1, page_size=5
        )

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
