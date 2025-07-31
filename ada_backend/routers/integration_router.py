from typing import Annotated
from uuid import UUID
from urllib.parse import urlencode

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_project_dependency,
)
from ada_backend.schemas.integration_schema import CreateProjectIntegrationSchema, IntegrationSecretResponse
from ada_backend.services.integration_service import add_integration_secrets_service
from ada_backend.repositories.integration_repository import insert_secret_integration
from engine.integrations.utils import exchange_slack_oauth_code, get_slack_oauth_access_token
from settings import get_settings

router = APIRouter(prefix="/project", tags=["Integrations"])


@router.put(
    "/{project_id}/integration/{integration_id}",
    response_model=IntegrationSecretResponse,
    summary="Add integration secret",
    tags=["Integrations"],
)
async def add_integration_secrets(
    integration_id: UUID,
    create_project_integration: CreateProjectIntegrationSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    sqlalchemy_db_session: Session = Depends(get_db),
) -> IntegrationSecretResponse:
    """Add integration secrets for a project.

    Args:
        integration_id: The UUID of the integration
        create_project_integration: Integration configuration data
        user: Authenticated user with writer access
        sqlalchemy_db_session: Database session

    Returns:
        IntegrationSecretResponse: Created integration secret details

    Raises:
        HTTPException: If user ID not found or internal server error
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return await add_integration_secrets_service(
            session=sqlalchemy_db_session,
            integration_id=integration_id,
            create_project_integration=create_project_integration,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.get(
    "/oauth/slack/authorize",
    summary="Initiate Slack OAuth flow",
    tags=["OAuth"],
)
async def slack_oauth_authorize(
    project_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.WRITER.value))
    ],
) -> RedirectResponse:
    """Redirect user to Slack OAuth authorization page.

    Args:
        project_id: The UUID of the project
        user: Authenticated user with writer access

    Returns:
        RedirectResponse: Redirect to Slack OAuth authorization URL

    Raises:
        HTTPException: If Slack OAuth is not configured
    """
    settings = get_settings()

    if not settings.SLACK_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Slack OAuth not configured")

    base_url = "https://slack.com/oauth/v2/authorize"
    redirect_uri = f"{settings.ADA_URL}/project/{project_id}/oauth/slack/callback"

    params = {
        "client_id": settings.SLACK_CLIENT_ID,
        "scope": "chat:write,channels:read,groups:read,im:read,mpim:read",
        "redirect_uri": redirect_uri,
        "state": str(project_id),
    }

    oauth_url = f"{base_url}?{urlencode(params)}"
    return RedirectResponse(url=oauth_url)


@router.get(
    "/{project_id}/oauth/slack/callback",
    summary="Handle Slack OAuth callback",
    tags=["OAuth"],
)
async def slack_oauth_callback(
    project_id: UUID,
    code: str,
    state: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    sqlalchemy_db_session: Session = Depends(get_db),
) -> dict:
    """Handle the OAuth callback from Slack and store the tokens.

    Args:
        project_id: The UUID of the project
        code: Authorization code from Slack
        state: State parameter for security validation
        user: Authenticated user with writer access
        sqlalchemy_db_session: Database session

    Returns:
        dict: Success response with integration secret details

    Raises:
        HTTPException: If state validation fails, OAuth not configured, or callback fails
    """
    settings = get_settings()

    if state != str(project_id):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    if not settings.SLACK_CLIENT_ID or not settings.SLACK_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Slack OAuth not configured")

    try:
        redirect_uri = f"{settings.ADA_URL}/project/{project_id}/oauth/slack/callback"
        access_token, refresh_token, expires_in, token_last_updated = exchange_slack_oauth_code(
            code=code,
            client_id=settings.SLACK_CLIENT_ID,
            client_secret=settings.SLACK_CLIENT_SECRET,
            redirect_uri=redirect_uri,
        )

        from ada_backend.database.seed.integrations.seed_integration import INTEGRATION_UUIDS

        slack_integration_id = INTEGRATION_UUIDS["slack_sender"]

        integration_secret = insert_secret_integration(
            session=sqlalchemy_db_session,
            integration_id=slack_integration_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            token_last_updated=token_last_updated,
        )

        return {
            "message": "Slack OAuth successful",
            "integration_secret_id": str(integration_secret.id),
            "project_id": str(project_id),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}") from e


@router.post(
    "/{project_id}/oauth/slack/refresh",
    summary="Refresh Slack OAuth token",
    tags=["OAuth"],
)
async def slack_oauth_refresh(
    project_id: UUID,
    secret_integration_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    sqlalchemy_db_session: Session = Depends(get_db),
) -> dict:
    """Manually refresh a Slack OAuth token.

    Args:
        project_id: The UUID of the project
        secret_integration_id: The UUID of the integration secret to refresh
        user: Authenticated user with writer access
        sqlalchemy_db_session: Database session

    Returns:
        dict: Success response with refreshed token details

    Raises:
        HTTPException: If Slack OAuth is not configured or token refresh fails
    """
    settings = get_settings()

    if not settings.SLACK_CLIENT_ID or not settings.SLACK_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Slack OAuth not configured")

    try:
        new_access_token = get_slack_oauth_access_token(
            session=sqlalchemy_db_session,
            integration_secret_id=secret_integration_id,
            slack_client_id=settings.SLACK_CLIENT_ID,
            slack_client_secret=settings.SLACK_CLIENT_SECRET,
        )

        return {"message": "Token refreshed successfully", "secret_integration_id": str(secret_integration_id)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {str(e)}") from e
