"""API key management tools (project-scoped and org-scoped)."""

from fastmcp import FastMCP

from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

_PROJECT_ID = Param("project_id", str, description="The project ID.")
_KEY_ID = Param("key_id", str, description="The API key ID to revoke.")
_KEY_NAME = Param("key_name", str, default="", description="Optional friendly name for the key.")

SPECS: list[ToolSpec] = [
    # --- Project-scoped ---
    ToolSpec(
        name="list_project_api_keys",
        description="List API keys for a project.",
        method="get",
        path="/auth/api-key",
        query_params=(_PROJECT_ID,),
        return_annotation=list,
    ),
    ToolSpec(
        name="create_project_api_key",
        description="Create a new API key scoped to a project. The key is shown only once.",
        method="post",
        path="/auth/api-key",
        body_fields=(_PROJECT_ID, _KEY_NAME),
    ),
    ToolSpec(
        name="revoke_project_api_key",
        description="Revoke a specific API key for a project.",
        method="delete",
        path="/auth/api-key",
        query_params=(_PROJECT_ID,),
        body_fields=(_KEY_ID,),
    ),
    # --- Org-scoped ---
    ToolSpec(
        name="list_org_api_keys",
        description="List API keys for the active organization.",
        method="get",
        path="/auth/org-api-key",
        scope="org",
        org_query_key="organization_id",
        return_annotation=list,
    ),
    ToolSpec(
        name="create_org_api_key",
        description="Create a new API key scoped to the active organization. The key is shown only once.",
        method="post",
        path="/auth/org-api-key",
        scope="org",
        body_fields=(_KEY_NAME,),
        body_org_key="org_id",
    ),
    ToolSpec(
        name="revoke_org_api_key",
        description="Revoke an API key for the active organization.",
        method="delete",
        path="/auth/org-api-key",
        scope="org",
        org_query_key="organization_id",
        body_fields=(_KEY_ID,),
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
