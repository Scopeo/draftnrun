"""Variable definitions, variable sets, and secrets management tools.

All tools in this module require admin or super_admin role.
"""

from fastmcp import FastMCP

from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools

ADMIN_ROLES = ("admin", "super_admin")

_VAR_NAME = Param("name", str, description="Variable name (unique within org).")
_SET_ID = Param("set_id", str, description="Variable set ID.")
_SECRET_KEY = Param("key", str, description="Secret key name.")

SPECS: list[ToolSpec] = [
    # --- Variable Definitions ---
    ToolSpec(
        name="list_variable_definitions",
        description="List all variable definitions in the active organization. Requires admin role.",
        method="get",
        path="/org/{org_id}/variable-definitions",
        scope="role",
        roles=ADMIN_ROLES,
        return_annotation=list,
    ),
    ToolSpec(
        name="upsert_variable_definition",
        description="Create or update a variable definition. Requires admin role.",
        method="put",
        path="/org/{org_id}/variable-definitions/{name}",
        scope="role",
        roles=ADMIN_ROLES,
        path_params=(_VAR_NAME,),
        body_param=Param(
            "definition", dict,
            description="Variable definition (type, default_value, description, etc.).",
        ),
    ),
    ToolSpec(
        name="delete_variable_definition",
        description="Delete a variable definition. Requires admin role.",
        method="delete",
        path="/org/{org_id}/variable-definitions/{name}",
        scope="role",
        roles=ADMIN_ROLES,
        path_params=(_VAR_NAME,),
    ),
    # --- Variable Sets ---
    ToolSpec(
        name="list_variable_sets",
        description="List all variable sets in the active organization. Requires admin role.",
        method="get",
        path="/org/{org_id}/variable-sets",
        scope="role",
        roles=ADMIN_ROLES,
        return_annotation=list,
    ),
    ToolSpec(
        name="upsert_variable_set",
        description="Create or update a variable set. Requires admin role.",
        method="put",
        path="/org/{org_id}/variable-sets/{set_id}",
        scope="role",
        roles=ADMIN_ROLES,
        path_params=(_SET_ID,),
        body_param=Param("data", dict, description="Variable set data (name, values, etc.)."),
    ),
    ToolSpec(
        name="delete_variable_set",
        description="Delete a variable set. Requires admin role.",
        method="delete",
        path="/org/{org_id}/variable-sets/{set_id}",
        scope="role",
        roles=ADMIN_ROLES,
        path_params=(_SET_ID,),
    ),
    # --- Secrets ---
    ToolSpec(
        name="list_secrets",
        description="List all secrets in the active organization (values are masked). Requires admin role.",
        method="get",
        path="/org/{org_id}/secrets",
        scope="role",
        roles=ADMIN_ROLES,
        return_annotation=list,
    ),
    ToolSpec(
        name="upsert_secret",
        description="Create or update a secret. Requires admin role.",
        method="put",
        path="/org/{org_id}/secrets/{key}",
        scope="role",
        roles=ADMIN_ROLES,
        path_params=(_SECRET_KEY,),
        body_fields=(
            Param("value", str, description="Secret value (stored encrypted)."),
            Param("description", str, default="", description="Optional description."),
        ),
    ),
    ToolSpec(
        name="delete_secret",
        description="Delete a secret. Requires admin role.",
        method="delete",
        path="/org/{org_id}/secrets/{key}",
        scope="role",
        roles=ADMIN_ROLES,
        path_params=(_SECRET_KEY,),
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, SPECS)
