from typing import Annotated
import logging
from uuid import UUID

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException

from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_project_dependency,
)
from ada_backend.schemas.integration_schema import CreateProjectIntegrationSchema, IntegrationSecretResponse
from ada_backend.services.integration_service import add_integration_secrets_service

router = APIRouter(prefix="/project", tags=["Integrations"])
LOGGER = logging.getLogger(__name__)


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
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value))
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
        LOGGER.exception(
            "Failed to add integration secrets for integration %s",
            integration_id,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
