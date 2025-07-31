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
from engine.integrations.utils import exchange_slack_oauth_code
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


# OAuth endpoints for Slack integration
@router.get(
    "/oauth/slack/authorize",
    summary="Initiate Slack OAuth flow",
    tags=["OAuth"],
)
async def slack_oauth_authorize(
    project_id: UUID,
    # user: Annotated[
    #     SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.WRITER.value))
    # ],
) -> RedirectResponse:
    """Redirect user to Slack OAuth authorization page."""
    settings = get_settings()

    if not settings.SLACK_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Slack OAuth not configured")

    # Build the OAuth URL
    base_url = "https://slack.com/oauth/v2/authorize"
    redirect_uri = f"{settings.ADA_URL}/project/{project_id}/oauth/slack/callback"

    params = {
        "client_id": settings.SLACK_CLIENT_ID,
        "scope": "chat:write,channels:read,groups:read,im:read,mpim:read",
        "redirect_uri": redirect_uri,
        "state": str(project_id),  # Pass project_id as state for security
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
    # user: Annotated[
    #     SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.WRITER.value))
    # ],
    sqlalchemy_db_session: Session = Depends(get_db),
) -> dict:
    """Handle the OAuth callback from Slack and store the tokens."""
    settings = get_settings()

    # Verify state parameter matches project_id for security
    if state != str(project_id):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    if not settings.SLACK_CLIENT_ID or not settings.SLACK_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Slack OAuth not configured")

    try:
        # Exchange authorization code for tokens
        redirect_uri = f"{settings.ADA_URL}/project/{project_id}/oauth/slack/callback"
        access_token, refresh_token, expires_in, token_last_updated = exchange_slack_oauth_code(
            code=code,
            client_id=settings.SLACK_CLIENT_ID,
            client_secret=settings.SLACK_CLIENT_SECRET,
            redirect_uri=redirect_uri,
        )

        # Get the Slack integration ID (you'll need to create this in your database)
        # For now, we'll use a placeholder - you should get this from your integrations table
        from ada_backend.database.seed.integrations.seed_integration import INTEGRATION_UUIDS

        slack_integration_id = INTEGRATION_UUIDS["slack_sender"]

        # Store the tokens in the database
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
    # user: Annotated[
    #     SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.WRITER.value))
    # ],
    sqlalchemy_db_session: Session = Depends(get_db),
) -> dict:
    """Manually refresh a Slack OAuth token."""
    settings = get_settings()

    if not settings.SLACK_CLIENT_ID or not settings.SLACK_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Slack OAuth not configured")

    try:
        from engine.integrations.utils import get_slack_oauth_access_token

        # This will automatically refresh the token if needed
        new_access_token = get_slack_oauth_access_token(
            session=sqlalchemy_db_session,
            integration_secret_id=secret_integration_id,
            slack_client_id=settings.SLACK_CLIENT_ID,
            slack_client_secret=settings.SLACK_CLIENT_SECRET,
        )

        return {"message": "Token refreshed successfully", "secret_integration_id": str(secret_integration_id)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token refresh failed: {str(e)}") from e
