"""
OAuth router.

Endpoints for managing OAuth connections (provider agnostic).
Supports both Supabase user auth and org/project API key auth.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.repositories.project_repository import get_project
from ada_backend.routers.auth_router import (
    VerifiedApiKey,
    verify_api_key_dependency,
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

_optional_bearer = HTTPBearer(auto_error=False)


def _verify_api_key_project_access(
    project_id: UUID,
    verified_api_key: VerifiedApiKey,
    session: Session,
) -> None:
    """Verify that the API key has access to the given project."""
    if verified_api_key.project_id is not None:
        if verified_api_key.project_id != project_id:
            raise HTTPException(status_code=403, detail="You don't have access to this project")
        return
    if verified_api_key.organization_id is not None:
        project = get_project(session, project_id=project_id)
        if not project or project.organization_id != verified_api_key.organization_id:
            raise HTTPException(status_code=403, detail="You don't have access to this project")
        return
    raise HTTPException(status_code=403, detail="API key has no valid scope")


async def _resolve_oauth_auth(
    project_id: UUID,
    session: Session,
    bearer_creds: HTTPAuthorizationCredentials | None,
    x_api_key: str | None,
) -> SupabaseUser | None:
    """
    Try Supabase bearer auth first, then API key auth.
    Returns SupabaseUser if bearer auth succeeded, None if API key auth succeeded.
    Raises HTTPException(401) if neither works.
    """
    # Try bearer token (Supabase)
    if bearer_creds:
        try:
            from ada_backend.routers.auth_router import supabase
            from settings import settings
            from ada_backend.services.request_context import get_request_context

            if settings.OFFLINE_MODE:
                return SupabaseUser(
                    id=UUID("11111111-1111-1111-1111-111111111111"),
                    email="dummy@email.com",
                    token="offline-mode-token",
                )

            user_response = supabase.auth.get_user(bearer_creds.credentials)
            if user_response and user_response.user:
                return SupabaseUser(
                    id=UUID(user_response.user.id),
                    email=user_response.user.email or "",
                    token=bearer_creds.credentials,
                )
        except Exception:
            pass  # Fall through to API key auth

    # Try API key
    if x_api_key:
        try:
            verified = await verify_api_key_dependency(x_api_key=x_api_key, session=session)
            _verify_api_key_project_access(project_id, verified, session)
            return None  # Authenticated via API key, no user context
        except HTTPException:
            pass  # Neither worked

    raise HTTPException(status_code=401, detail="Authentication required")


@router.get("/oauth/health", summary="Check OAuth service health")
async def oauth_health() -> dict:
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
    session: Session = Depends(get_db),
    bearer_creds: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> OAuthURLResponse:
    """
    Generate OAuth URL for headless flow (no Connect UI).

    Returns a direct URL to the provider's OAuth page.
    Accepts either Supabase user auth (Bearer token) or org/project API key (X-API-Key header).
    """
    await _resolve_oauth_auth(project_id, session, bearer_creds, x_api_key)

    try:
        result = await integration_service.create_oauth_authorization(
            project_id=project_id,
            provider_config_key=request.provider_config_key.value,
            end_user_email=request.end_user_email,
            external_user_id=request.external_user_id,
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
    session: Session = Depends(get_db),
    bearer_creds: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> OAuthConnectionResponse:
    """
    Confirm OAuth connection after user completes flow in browser.

    Verifies connection exists in Nango and creates record in our DB.
    Accepts either Supabase user auth (Bearer token) or org/project API key (X-API-Key header).
    """
    supabase_user = await _resolve_oauth_auth(project_id, session, bearer_creds, x_api_key)

    try:
        connection_id = await integration_service.confirm_oauth_connection(
            session=session,
            project_id=project_id,
            provider_config_key=request.provider_config_key.value,
            created_by_user_id=supabase_user.id if supabase_user else None,
            name=request.name,
            external_user_id=request.external_user_id,
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
    session: Session = Depends(get_db),
    external_user_id: str | None = Query(None),
    bearer_creds: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> OAuthConnectionStatusResponse:
    """
    Check if an OAuth connection exists and is active for a project.
    Accepts either Supabase user auth (Bearer token) or org/project API key (X-API-Key header).
    """
    await _resolve_oauth_auth(project_id, session, bearer_creds, x_api_key)

    result = await integration_service.check_connection_status(
        session=session,
        project_id=project_id,
        provider_config_key=provider_config_key.value,
        external_user_id=external_user_id,
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
    session: Session = Depends(get_db),
    bearer_creds: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> dict:
    """
    Revoke and delete an OAuth connection.
    Accepts either Supabase user auth (Bearer token) or org/project API key (X-API-Key header).
    """
    await _resolve_oauth_auth(project_id, session, bearer_creds, x_api_key)

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
