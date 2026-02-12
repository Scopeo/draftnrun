"""
OAuth router.

Endpoints for managing OAuth connections (provider agnostic).
Connections are scoped to organizations.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.oauth_schemas import (
    CreateOAuthConnectionRequest,
    OAuthConnectionListItem,
    OAuthConnectionResponse,
    OAuthConnectionStatusResponse,
    OAuthURLResponse,
    UpdateOAuthConnectionRequest,
)
from ada_backend.services import integration_service
from ada_backend.services.errors import (
    NangoConnectionNotFoundError,
    OAuthConnectionNotFoundError,
    OAuthConnectionUnauthorizedError,
)
from ada_backend.services.nango_client import NangoClientError, get_nango_client
from engine.integrations.providers import OAuthProvider

router = APIRouter(tags=["OAuth"])
LOGGER = logging.getLogger(__name__)


@router.get("/oauth/health", summary="Check OAuth service health")
async def oauth_health() -> dict:
    nango_healthy = await get_nango_client().health_check()
    return {"status": "ok" if nango_healthy else "degraded"}


@router.get(
    "/organizations/{organization_id}/oauth-connections",
    response_model=list[OAuthConnectionListItem],
    summary="List OAuth connections for organization",
)
async def list_oauth_connections(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
    provider_config_key: Annotated[OAuthProvider | None, Query()] = None,
) -> list[OAuthConnectionListItem]:
    """List all OAuth connections for an organization, optionally filtered by provider."""
    return integration_service.list_oauth_connections(
        session=session,
        organization_id=organization_id,
        provider_config_key=str(provider_config_key) if provider_config_key else None,
    )


@router.post(
    "/organizations/{organization_id}/oauth-connections/authorize",
    response_model=OAuthURLResponse,
    summary="Start OAuth authorization flow (headless)",
)
async def start_oauth_authorization(
    organization_id: UUID,
    request: CreateOAuthConnectionRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
) -> OAuthURLResponse:
    """
    Generate OAuth URL for headless flow (no Connect UI).

    Returns a direct URL to the provider's OAuth page and pending_connection_id to pass to confirm.
    """
    try:
        result = await integration_service.create_oauth_authorization(
            organization_id=organization_id,
            provider_config_key=request.provider_config_key.value,
            end_user_email=request.end_user_email,
        )

        return OAuthURLResponse(
            oauth_url=result.oauth_url,
            pending_connection_id=result.pending_connection_id,
        )
    except (OAuthConnectionNotFoundError, NangoConnectionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except NangoClientError as e:
        LOGGER.exception("Failed to create OAuth connect session")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception("Failed to generate OAuth URL")
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post(
    "/organizations/{organization_id}/oauth-connections",
    response_model=OAuthConnectionResponse,
    summary="Confirm OAuth connection after user completes flow",
)
async def create_oauth_connection(
    organization_id: UUID,
    request: CreateOAuthConnectionRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> OAuthConnectionResponse:
    """
    Confirm OAuth connection after user completes flow in browser.

    Requires pending_connection_id from authorize response.
    Verifies connection exists in Nango and creates record in our DB.
    """
    if not request.pending_connection_id:
        raise HTTPException(
            status_code=400,
            detail="pending_connection_id is required. Obtain it from the authorize endpoint.",
        )
    try:
        connection = await integration_service.confirm_oauth_connection(
            session=session,
            organization_id=organization_id,
            pending_connection_id=request.pending_connection_id,
            provider_config_key=request.provider_config_key.value,
            created_by_user_id=user.id,
            name=request.name,
        )

        return OAuthConnectionResponse(
            connection_id=connection.id,
            provider_config_key=connection.provider_config_key,
            name=connection.name,
        )
    except NangoConnectionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except NangoClientError as e:
        LOGGER.exception("OAuth connection confirmation failed")
        raise HTTPException(status_code=e.status_code or 500, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception("OAuth connection confirmation failed")
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.get(
    "/organizations/{organization_id}/oauth-connections/status",
    response_model=OAuthConnectionStatusResponse,
    summary="Check OAuth connection status",
)
async def get_oauth_connection_status(
    organization_id: UUID,
    provider_config_key: OAuthProvider,
    connection_id: Annotated[UUID, Query(description="OAuth connection ID to check")],
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> OAuthConnectionStatusResponse:
    """Check if a specific OAuth connection is active. organization_id validates ownership."""
    result = await integration_service.check_connection_status(
        session=session,
        organization_id=organization_id,
        connection_id=connection_id,
        provider_config_key=provider_config_key.value,
    )

    return OAuthConnectionStatusResponse(
        connected=result.connected,
        provider_config_key=result.provider_config_key,
        connection_id=result.connection_id,
        name=result.name,
    )


@router.patch(
    "/organizations/{organization_id}/oauth-connections/{connection_id}",
    response_model=OAuthConnectionResponse,
    summary="Update OAuth connection name",
)
async def update_oauth_connection_name(
    organization_id: UUID,
    connection_id: UUID,
    data: UpdateOAuthConnectionRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> OAuthConnectionResponse:
    """Update the display name of an OAuth connection. Validates ownership via organization_id."""
    new_name = data.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name cannot be empty after trimming")

    connection = await integration_service.update_oauth_connection_name(
        session=session,
        organization_id=organization_id,
        connection_id=connection_id,
        new_name=new_name,
    )

    return OAuthConnectionResponse(
        connection_id=connection.id,
        provider_config_key=connection.provider_config_key,
        name=connection.name,
    )


@router.delete(
    "/organizations/{organization_id}/oauth-connections/{connection_id}",
    summary="Revoke OAuth connection",
)
async def delete_oauth_connection(
    organization_id: UUID,
    connection_id: UUID,
    provider_config_key: OAuthProvider,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    """Revoke and delete an OAuth connection."""
    try:
        await integration_service.revoke_oauth_connection(
            session=session,
            organization_id=organization_id,
            connection_id=connection_id,
            provider_config_key=provider_config_key.value,
        )

        return {"success": True, "message": "Connection revoked"}
    except OAuthConnectionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except OAuthConnectionUnauthorizedError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception("OAuth revoke failed")
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
