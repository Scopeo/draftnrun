"""
OAuth router.

Endpoints for managing OAuth connections (provider agnostic).
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_project_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.oauth_schemas import (
    CreateOAuthConnectionRequest,
    OAuthConnectionResponse,
    OAuthConnectionStatusResponse,
    OAuthURLResponse,
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
    """Check if Nango is healthy."""
    nango_healthy = await get_nango_client().health_check()
    return {"status": "ok" if nango_healthy else "degraded"}


@router.post(
    "/projects/{project_id}/oauth-connections/authorize",
    response_model=OAuthURLResponse,
    summary="Start OAuth authorization flow (headless)",
)
async def start_oauth_authorization(
    project_id: UUID,
    request: CreateOAuthConnectionRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
) -> OAuthURLResponse:
    """
    Generate OAuth URL for headless flow (no Connect UI).

    Returns a direct URL to the provider's OAuth page.
    """
    try:
        result = await integration_service.create_oauth_authorization(
            project_id=project_id,
            provider_config_key=request.provider_config_key.value,
            end_user_email=request.end_user_email,
        )

        return OAuthURLResponse(
            oauth_url=result.oauth_url,
            end_user_id=result.end_user_id,
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
    "/projects/{project_id}/oauth-connections",
    response_model=OAuthConnectionResponse,
    summary="Confirm OAuth connection after user completes flow",
)
async def create_oauth_connection(
    project_id: UUID,
    request: CreateOAuthConnectionRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> OAuthConnectionResponse:
    """
    Confirm OAuth connection after user completes flow in browser.

    Verifies connection exists in Nango and creates record in our DB.
    """
    try:
        connection_id = await integration_service.confirm_oauth_connection(
            session=session,
            project_id=project_id,
            provider_config_key=request.provider_config_key.value,
            created_by_user_id=user.id,
            name=request.name,
        )

        return OAuthConnectionResponse(
            connection_id=connection_id,
            provider_config_key=request.provider_config_key.value,
            name=request.name,
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
    "/projects/{project_id}/oauth-connections/status",
    response_model=OAuthConnectionStatusResponse,
    summary="Check OAuth connection status for a project",
)
async def get_oauth_connection_status(
    project_id: UUID,
    provider_config_key: OAuthProvider,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> OAuthConnectionStatusResponse:
    """Check if an OAuth connection exists and is active for a project."""
    result = await integration_service.check_connection_status(
        session=session,
        project_id=project_id,
        provider_config_key=provider_config_key.value,
    )

    return OAuthConnectionStatusResponse(
        connected=result.connected,
        provider_config_key=result.provider_config_key,
        connection_id=result.connection_id,
        name=result.name,
    )


@router.delete(
    "/projects/{project_id}/oauth-connections/{connection_id}",
    summary="Revoke OAuth connection",
)
async def delete_oauth_connection(
    project_id: UUID,
    connection_id: UUID,
    provider_config_key: OAuthProvider,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    """Revoke and delete an OAuth connection."""
    try:
        await integration_service.revoke_oauth_connection(
            session=session,
            project_id=project_id,
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
