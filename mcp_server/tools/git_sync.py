"""Git sync tools — import projects from a GitHub repo for one-way graph deployment."""

from uuid import UUID

from fastmcp import FastMCP

from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

_GITHUB_OWNER = Param("github_owner", str, description="GitHub repository owner (user or organization name).")
_GITHUB_REPO_NAME = Param("github_repo_name", str, description="GitHub repository name.")
_BRANCH = Param("branch", str, default="main", description="Branch to watch (default: main).")
_GITHUB_INSTALLATION_ID = Param(
    "github_installation_id",
    int,
    description="GitHub App installation ID (from the GitHub App install page).",
)
_PROJECT_TYPE = Param(
    "project_type",
    str,
    default="workflow",
    description="Type of project to create: 'workflow' or 'agent' (default: workflow).",
)
_CONFIG_ID = Param(
    "config_id", UUID, description="Git sync config ID (from list_git_sync_configs or configure_git_sync)."
)

SPECS: list[ToolSpec] = [
    ToolSpec(
        name="configure_git_sync",
        description=(
            "Scan a GitHub repository for graph.json files and create a Draft'n Run project + sync config "
            "for each one found. On each push to the watched branch, the backend fetches graph.json "
            "and deploys it to production (draft is never touched). "
            "A single repo can contain multiple projects (one graph.json per subfolder). "
            "Folders already linked to a project are skipped. "
            "Requires: the Draft'n Run GitHub App installed on the repo, and the installation ID. Developer+."
        ),
        method="post",
        path="/organizations/{org_id}/git-sync",
        scope="role",
        roles=("developer", "admin", "super_admin"),
        body_fields=(_GITHUB_OWNER, _GITHUB_REPO_NAME, _BRANCH, _GITHUB_INSTALLATION_ID, _PROJECT_TYPE),
    ),
    ToolSpec(
        name="list_git_sync_configs",
        description="List all git sync configurations in the active organization.",
        method="get",
        path="/organizations/{org_id}/git-sync",
        scope="org",
        return_annotation=list,
    ),
    ToolSpec(
        name="get_git_sync_config",
        description="Get details of a specific git sync configuration, including last sync status.",
        method="get",
        path="/organizations/{org_id}/git-sync/{config_id}",
        scope="org",
        path_params=(_CONFIG_ID,),
    ),
    ToolSpec(
        name="disconnect_git_sync",
        description=(
            "Remove git sync for a project. The GitHub App installation is not affected "
            "(managed by the user on GitHub). Existing production deployments remain."
        ),
        method="delete",
        path="/organizations/{org_id}/git-sync/{config_id}",
        scope="role",
        roles=("developer", "admin", "super_admin"),
        path_params=(_CONFIG_ID,),
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
