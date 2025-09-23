from typing import Annotated, List
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser, VerifiedApiKey
from ada_backend.schemas.source_schema import DataSourceSchema, DataSourceSchemaResponse

from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
    verify_api_key_dependency,
    verify_ingestion_api_key_dependency,
)
from ada_backend.services.source_service import (
    get_sources_by_organization,
    create_source_by_organization,
    delete_source_service,
    update_source_by_source_id,
)

router = APIRouter(prefix="/sources", tags=["Sources"])
LOGGER = logging.getLogger(__name__)


@router.get("/{organization_id}", response_model=List[DataSourceSchemaResponse])
def get_organization_sources(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_sources_by_organization(session, organization_id)
    except Exception as e:
        LOGGER.exception(
            "Failed to get sources for organization %s",
            organization_id,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post("/{organization_id}", status_code=status.HTTP_201_CREATED)
def create_organization_source(
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    organization_id: UUID,
    source: DataSourceSchema,
    session: Session = Depends(get_db),
) -> UUID:
    try:
        source_id = create_source_by_organization(session, organization_id, source)
        return source_id
    except Exception as e:
        LOGGER.exception(
            "Failed to create source for organization %s",
            organization_id,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post("/{organization_id}/{source_id}", status_code=status.HTTP_200_OK)
def update_organization_source(
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    organization_id: UUID,
    source_id: UUID,
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return update_source_by_source_id(session, organization_id, source_id, user_id=user.id)
    except Exception as e:
        LOGGER.exception(
            "Failed to update source %s for organization %s by user %s",
            source_id,
            organization_id,
            user.id,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post("/{organization_id}/{source_id}/api-key", status_code=status.HTTP_200_OK)
def update_organization_source_api_key(
    organization_id: UUID,
    source_id: UUID,
    session: Session = Depends(get_db),
    verified_api_key: VerifiedApiKey = Depends(verify_api_key_dependency),
):
    if verified_api_key.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="You don't have access to this organization")
    try:
        return update_source_by_source_id(session, organization_id, source_id, api_key_id=verified_api_key.api_key_id)

    except Exception as e:
        LOGGER.exception(
            "Failed to update source API key %s for organization %s",
            source_id,
            organization_id,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.delete("/{organization_id}/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization_source(
    organization_id: UUID,
    source_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        delete_source_service(session, organization_id, source_id)
        return None
    except Exception as e:
        LOGGER.exception(
            "Failed to delete source %s for organization %s",
            source_id,
            organization_id,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
