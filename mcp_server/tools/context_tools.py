"""Organization context and membership tools.

These tools manage the user's active organization session and provide
access to org membership data via direct Supabase queries.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token
from pydantic import Field

from mcp_server import context as _ctx
from mcp_server.auth.supabase_client import (
    fetch_org_release_stage,
    get_org_members,
    invite_member,
    list_user_organizations,
)
from mcp_server.context import get_active_org, set_active_org


def _get_auth() -> tuple[str, str]:
    """Return (raw_jwt, user_id) from the current MCP request."""
    token = get_access_token()
    if token is None:
        raise ValueError(
            "Not authenticated. The MCP client may need to complete the OAuth flow — "
            "check your client's MCP server status and reconnect if needed."
        )
    user_id = token.claims.get("sub", "")
    if not user_id:
        raise ValueError(
            "Token missing user identity (sub claim). "
            "This usually means the OAuth token is malformed — reconnect to the MCP server."
        )
    return token.token, user_id


async def _require_target_org_role(jwt: str, user_id: str, org_id: str, *allowed_roles: str, action: str = "") -> dict:
    orgs = await list_user_organizations(jwt, user_id)
    match = next((org for org in orgs if org["id"] == org_id), None)
    if not match:
        raise ValueError(f"Organization {org_id} not found in your memberships.")
    if match["role"] not in allowed_roles:
        context = f"{action} in organization {org_id}" if action else f"This operation on organization {org_id}"
        raise ValueError(
            f"{context} requires one of {allowed_roles} role, "
            f"but your role there is '{match['role']}'."
        )
    return match


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_my_organizations() -> list[dict]:
        """List all organizations you belong to, with your role in each."""
        jwt, user_id = _get_auth()
        return await list_user_organizations(jwt, user_id)

    @mcp.tool()
    async def select_organization(
        organization_id: Annotated[
            UUID,
            Field(
                description=(
                    "The organization ID (from list_my_organizations). Never invent this value."
                ),
            ),
        ],
    ) -> dict:
        """Set your active organization for this session.

        All subsequent org-scoped tools will operate on this organization.
        Use list_my_organizations first to see available orgs.
        """
        jwt, user_id = _get_auth()
        orgs = await list_user_organizations(jwt, user_id)
        match = next((o for o in orgs if o["id"] == str(organization_id)), None)
        if not match:
            raise ValueError(f"Organization {organization_id} not found in your memberships.")
        release_stage = await fetch_org_release_stage(jwt, match["id"])
        await set_active_org(user_id, match["id"], match["name"], match["role"], release_stage)
        return {
            "status": "ok",
            "org_id": match["id"],
            "org_name": match["name"],
            "role": match["role"],
            "release_stage": release_stage,
        }

    @mcp.tool()
    async def get_current_context() -> dict:
        """Show your current session: active organization, user info, and session diagnostics."""
        token_obj = get_access_token()
        if token_obj is None:
            raise ValueError("Not authenticated.")
        user_id = token_obj.claims.get("sub", "")
        if not user_id:
            raise ValueError("Token missing user identity (sub claim).")
        org = await get_active_org(user_id)
        session_id = _ctx._current_session_id()
        return {
            "user_id": user_id,
            "email": token_obj.claims.get("email", "unknown"),
            "active_organization": org,
            "session": {
                "session_id": session_id,
                "storage_backend": "memory" if _ctx._using_memory else "redis",
            },
        }

    @mcp.tool()
    async def list_org_members(
        organization_id: Annotated[UUID, Field(description="The organization ID (from list_my_organizations).")],
    ) -> list[dict]:
        """List members of an organization with their roles."""
        jwt, user_id = _get_auth()
        org_id_str = str(organization_id)
        await _require_target_org_role(
            jwt, user_id, org_id_str, "member", "developer", "admin", "super_admin",
            action="Listing members",
        )
        return await get_org_members(jwt, org_id_str)

    @mcp.tool()
    async def invite_org_member(
        organization_id: Annotated[UUID, Field(description="Target organization ID (from list_my_organizations).")],
        email: Annotated[str, Field(description="Email address of the person to invite.")],
        role: Annotated[
            Literal["member", "developer", "admin"],
            Field(description="Role to assign."),
        ] = "member",
    ) -> dict:
        """Invite a user to an organization by email. Requires admin role."""
        jwt, user_id = _get_auth()
        org_id_str = str(organization_id)
        await _require_target_org_role(
            jwt, user_id, org_id_str, "admin", "super_admin", action="Inviting members",
        )
        return await invite_member(jwt, org_id_str, email, role)
