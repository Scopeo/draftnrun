from typing import Annotated, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

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
    upsert_source_by_organization,
    delete_source_service,
)

router = APIRouter(prefix="/sources", tags=["Sources"])


@router.get("/{organization_id}", response_model=List[DataSourceSchemaResponse])
async def get_organization_sources(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: AsyncSession = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return await get_sources_by_organization(session, organization_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post("/{organization_id}", status_code=status.HTTP_201_CREATED)
async def create_organization_source(
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    organization_id: UUID,
    source: DataSourceSchema,
    session: AsyncSession = Depends(get_db),
) -> UUID:
    try:
        source_id = await create_source_by_organization(session, organization_id, source)
        return source_id
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.patch("/{organization_id}", status_code=status.HTTP_200_OK)
async def update_organization_source(
    organization_id: UUID,
    source: DataSourceUpdateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: AsyncSession = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        await upsert_source_by_organization(session, organization_id, source)
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.delete("/{organization_id}/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_source(
    organization_id: UUID,
    source_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: AsyncSession = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        await delete_source_service(session, organization_id, source_id)
        return None
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
