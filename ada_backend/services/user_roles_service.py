from typing import Any
from uuid import UUID
import httpx

from ada_backend.schemas.auth_schema import SupabaseUser, OrganizationAccess
from ada_backend.segment_analytics import identify_user_access_org
from settings import settings


async def _get_user_access(
    edge_function_endpoint: str,
    jwt_token: str,
    identifier_key: str,
    identifier_value: str,
) -> dict[str, Any]:
    """
    Generic function to check access for an organization or project,
    Using supabase edge functions.

    Parameters:
    - endpoint (str): The API endpoint to call.
    - jwt_token (str): The JWT token for authentication.
    - identifier_key (str): The key for the identifier (e.g., 'org_id' or 'project_id').
    - identifier_value (str): The identifier value to be checked.

    Returns:
    - dict: The response data containing access and role information.
    """
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }

    payload = {identifier_key: identifier_value}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            edge_function_endpoint,
            headers=headers,
            json=payload,
            timeout=10,
        )

    if response.status_code == 200:
        return response.json()

    return {"error": response.status_code, "message": response.text}


async def get_user_access_to_organization(
    user: SupabaseUser,
    organization_id: UUID,
) -> OrganizationAccess:
    """
    Check if a user has access to an organization.
    """
    # Offline mode bypass - always grant access with fixed role
    if settings.OFFLINE_MODE:
        return OrganizationAccess(org_id=organization_id, role=settings.OFFLINE_DEFAULT_ROLE)

    endpoint = f"{settings.SUPABASE_PROJECT_URL}/functions/v1/check-org-access"
    result = await _get_user_access(endpoint, user.token, "org_id", str(organization_id))
    identify_user_access_org(user.id, user.email, organization_id)

    if "error" in result:
        raise ValueError(result["message"])

    if not result["access"]:
        raise ValueError("User does not have access to organization")

    return OrganizationAccess(org_id=organization_id, role=result["role"])


async def is_user_super_admin(user: SupabaseUser) -> bool:
    """
    Check global super admin status using the same Edge Function as the frontend.
    """
    # Offline mode bypass - always return True
    if settings.OFFLINE_MODE:
        return True

    endpoint = f"{settings.SUPABASE_PROJECT_URL}/functions/v1/check-super-admin"
    headers = {
        "Authorization": f"Bearer {user.token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            endpoint,
            headers=headers,
            timeout=10,
        )
    if response.status_code == 200:
        data = response.json() if response.content else {}
        return bool(data.get("is_super_admin", False))
    return False
