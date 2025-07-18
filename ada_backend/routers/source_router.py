from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.source_schema import DataSourceSchema, DataSourceSchemaResponse, DataSourceUpdateSchema
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
    verify_ingestion_api_key_dependency,
)
from ada_backend.services.source_service import (
    get_sources_by_organization,
    create_source_by_organization,
    update_source_by_id,
    upsert_source_by_organization,
    delete_source_service,
)

router = APIRouter(prefix="/sources", tags=["Sources"])


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
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.get("/{organization_id}/ingestion", response_model=List[DataSourceSchemaResponse])
def get_organization_sources_ingestion(
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    organization_id: UUID,
    session: Session = Depends(get_db),
):
    """Get all sources for an organization using ingestion API key authentication."""
    try:
        return get_sources_by_organization(session, organization_id)
    except Exception as e:
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
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.patch("/{source_id}", status_code=status.HTTP_200_OK)
def update_source(
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    source_id: UUID,
    source: DataSourceSchema,
    session: Session = Depends(get_db),
) -> None:
    """
    Update an existing source by its ID.
    This endpoint updates a source using its unique ID.
    """
    try:
        update_source_by_id(session, source_id, source)
        return None
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.patch("/{organization_id}", status_code=status.HTTP_200_OK)
def update_organization_source(
    organization_id: UUID,
    source: DataSourceUpdateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        upsert_source_by_organization(session, organization_id, source)
        return None
    except Exception as e:
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
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
