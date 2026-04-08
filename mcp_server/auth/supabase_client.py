"""Direct Supabase client for org/member data.

Mirrors the frontend's direct Supabase queries (organization_members + organizations
tables) and Edge Function calls, using httpx with the user's Supabase JWT.
"""

import logging
from typing import Any
from uuid import UUID

import httpx

from mcp_server.client import ToolError
from mcp_server.settings import settings

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return settings.SUPABASE_PROJECT_URL.rstrip("/")


def _headers(jwt: str) -> dict[str, str]:
    return {
        "apikey": settings.SUPABASE_PROJECT_KEY,
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }


async def list_user_organizations(jwt: str, user_id: str) -> list[dict[str, Any]]:
    """Fetch user's organizations — same two-step query the frontend uses.

    1. GET organization_members filtered by user_id → list of org_ids + roles
    2. GET organizations filtered by those IDs → org names

    The public.organization_members table has no RLS, so we must filter
    explicitly by user_id (matching the front-end's .eq('user_id', userId)).
    """
    base = _base_url()
    headers = _headers(jwt)

    async with httpx.AsyncClient(timeout=settings.MCP_REQUEST_TIMEOUT) as client:
        memberships_resp = await client.get(
            f"{base}/rest/v1/organization_members",
            headers=headers,
            params={"select": "org_id,role", "user_id": f"eq.{user_id}"},
        )
        if memberships_resp.status_code != 200:
            raise ToolError(
                f"Failed to fetch your organization memberships (HTTP {memberships_resp.status_code}). "
                f"Your session may have expired — reconnect to refresh."
            )

        memberships = memberships_resp.json()
        if not memberships:
            return []

        valid_org_ids = []
        role_map = {}
        for m in memberships:
            raw_id = m["org_id"]
            try:
                UUID(raw_id)
            except (ValueError, AttributeError):
                logger.warning("Skipping membership with invalid org_id: %s", raw_id)
                continue
            valid_org_ids.append(raw_id)
            role_map[raw_id] = m["role"]

        if not valid_org_ids:
            return []

        org_id_filter = ",".join(valid_org_ids)
        orgs_resp = await client.get(
            f"{base}/rest/v1/organizations",
            headers=headers,
            params={"select": "id,name", "id": f"in.({org_id_filter})"},
        )
        if orgs_resp.status_code != 200:
            raise ToolError(
                f"Failed to fetch organization details (HTTP {orgs_resp.status_code}). "
                f"Your session may have expired — reconnect to refresh."
            )

        orgs = orgs_resp.json()
        return [
            {"id": org["id"], "name": org["name"], "role": role_map.get(org["id"], "member")}
            for org in orgs
        ]


async def get_org_members(jwt: str, org_id: str) -> list[dict[str, Any]]:
    """Get organization members via Supabase Edge Function."""
    base = _base_url()
    headers = _headers(jwt)

    async with httpx.AsyncClient(timeout=settings.MCP_REQUEST_TIMEOUT) as client:
        resp = await client.post(
            f"{base}/functions/v1/get-organization-members-details",
            headers=headers,
            json={"organization_id": org_id},
        )
        if resp.status_code != 200:
            raise ToolError(
                f"Failed to fetch organization members (HTTP {resp.status_code}). "
                f"Check your permissions or reconnect."
            )
        return resp.json()


async def fetch_org_release_stage(jwt: str, org_id: str) -> str:
    """Fetch the org's release stage from Supabase. Defaults to 'public'."""
    base = _base_url()
    headers = _headers(jwt)

    async with httpx.AsyncClient(timeout=settings.MCP_REQUEST_TIMEOUT) as client:
        resp = await client.get(
            f"{base}/rest/v1/organization_release_stages",
            headers=headers,
            params={
                "select": "release_stage_id,release_stages(name)",
                "org_id": f"eq.{org_id}",
                "limit": "1",
            },
        )
        if resp.status_code != 200:
            logger.warning("Failed to fetch org release stage: %s", resp.text[:200])
            return "public"

        rows = resp.json()
        if not rows:
            return "public"

        release_stages = rows[0].get("release_stages")
        if not isinstance(release_stages, dict):
            return "public"
        stage_name = release_stages.get("name")
        if not isinstance(stage_name, str) or not stage_name.strip():
            return "public"
        normalized = stage_name.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized not in ("internal", "beta", "early_access", "public"):
            return "public"
        return normalized


async def invite_member(jwt: str, org_id: str, email: str, role: str) -> dict[str, Any]:
    """Invite a member to an organization via Supabase Edge Function."""
    base = _base_url()
    headers = _headers(jwt)

    async with httpx.AsyncClient(timeout=settings.MCP_REQUEST_TIMEOUT) as client:
        resp = await client.post(
            f"{base}/functions/v1/invite-member",
            headers=headers,
            json={"organization_id": org_id, "email": email, "role": role},
        )
        if resp.status_code != 200:
            raise ToolError(f"Invite failed ({resp.status_code}): {resp.text[:200]}")
        return resp.json()
