from typing import Annotated, List
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.source_schema import DataSourceSchema, DataSourceSchemaResponse

from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
    verify_ingestion_api_key_dependency,
    user_has_access_to_organization_xor_verify_api_key,
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


@router.post(
    "/{organization_id}/{source_id}",
    status_code=status.HTTP_200_OK,
    summary="Update source in organization, authentication via user token or API key",
)
def update_organization_source(
    organization_id: UUID,
    source_id: UUID,
    auth_ids: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Update organization source with flexible authentication.
    """
    user_id, api_key_id = auth_ids
    try:
        if user_id:
            return update_source_by_source_id(session, organization_id, source_id, user_id=user_id)
        else:
            return update_source_by_source_id(session, organization_id, source_id, api_key_id=api_key_id)
    except Exception as e:
        LOGGER.exception(
            "Failed to update source %s for organization %s",
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
