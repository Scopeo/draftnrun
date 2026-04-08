"""Agent management tools."""

from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field

from mcp_server.client import api
from mcp_server.context import require_role
from mcp_server.tools._defaults import generate_entity_defaults
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

PROXY_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_agents",
        description=(
            "List all agents in the active organization. "
            "Each entry includes the agent_id needed for get_agent and configure_agent."
        ),
        method="get",
        path="/org/{org_id}/agents",
        scope="org",
        return_annotation=list,
    ),
    ToolSpec(
        name="get_agent",
        description=(
            "Get details of a specific agent version. "
            "Returns model_parameters, tools, and system_prompt. Use configure_agent to modify."
        ),
        method="get",
        path="/agents/{agent_id}/versions/{graph_runner_id}",
        path_params=(
            Param("agent_id", UUID, description="The agent (project) ID (from list_agents or create_agent)."),
            Param("graph_runner_id", UUID, description="The graph runner version ID (from get_project_overview)."),
        ),
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, PROXY_SPECS)

    @mcp.tool()
    async def create_agent(
        name: Annotated[str, Field(description="Agent name. Must not be empty or whitespace-only.")],
        description: Annotated[str, Field(description="Optional description.")] = "",
    ) -> dict:
        """Create a new agent in the active organization.

        An agent is a single AI node that is also the start node.  It receives
        messages and optionally uses tools.  If the user needs a separate Start
        node, custom payload fields, or a multi-step DAG, use
        `create_workflow` instead.

        Requires developer role or above. Auto-generates a unique ID, icon,
        and color. Use `configure_agent` afterwards to set the system prompt,
        model, and tools.
        """
        name = name.strip()
        if not name:
            raise ValueError("Agent name must not be empty or whitespace-only.")

        jwt, user_id = _get_auth()
        org = await require_role(user_id, "developer", "admin", "super_admin")
        defaults = generate_entity_defaults()
        return await api.post(
            f"/org/{org['org_id']}/agents",
            jwt,
            json={
                "id": defaults["id"],
                "name": name,
                "description": description,
                "icon": defaults["icon"],
                "icon_color": defaults["icon_color"],
            },
        )
