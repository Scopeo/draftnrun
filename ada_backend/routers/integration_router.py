from datetime import datetime
from typing import Annotated, Optional
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
from ada_backend.services.integration_sevice import add_or_update_integration_secrets_service

router = APIRouter(prefix="/project", tags=["Integrations"])


@router.put(
    "/{project_id}/integration/{integration_id}",
    response_model=IntegrationSecretResponse,
    summary="Add or update integration secret",
    tags=["Integrations"],
)
async def add_or_update_integration_secrets(
    project_id: UUID,
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
        return await add_or_update_integration_secrets_service(
            session=sqlalchemy_db_session,
            project_id=project_id,
            integration_id=integration_id,
            create_project_integration=create_project_integration,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
