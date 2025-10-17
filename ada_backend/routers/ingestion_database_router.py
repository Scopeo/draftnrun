import logging
from fastapi import APIRouter
from typing import Annotated
from fastapi import Depends, HTTPException, Query, Response, status
from uuid import UUID

from engine.storage_service.db_utils import DBDefinition
from ada_backend.routers.auth_router import (
    verify_ingestion_api_key_dependency,
    user_has_access_to_organization_dependency,
    UserRights,
    SupabaseUser,
)
from ada_backend.schemas.ingestion_database_schema import (
    ChunkData,
    PaginatedChunkDataResponse,
    UpdateChunk,
)
from ada_backend.services.ingestion_database_service import (
    create_table_in_ingestion_db,
    get_paginated_chunks_from_ingestion_db,
    update_chunk_info_in_ingestion_db,
    delete_chunks_from_ingestion_db,
)


router = APIRouter(tags=["Ingestion Database"])
LOGGER = logging.getLogger(__name__)


@router.post("/organizations/{organization_id}/ingestion_database")
def create_table_in_database(
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    organization_id: UUID,
    source_name: str,
    table_definition: DBDefinition,
) -> tuple[str, DBDefinition]:
    try:
        table_name, table_definition = create_table_in_ingestion_db(organization_id, source_name, table_definition)
        return table_name, table_definition
    except Exception as e:
        LOGGER.exception(
            "Failed to create table in database for organization %s, source %s",
            organization_id,
            source_name,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/organizations/{organization_id}/ingestion_database/sources/{source_name}/chunks")
def get_chunks_in_database(
    organization_id: UUID,
    source_name: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(10, ge=1, le=1000, description="Number of items per page"),
) -> PaginatedChunkDataResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_paginated_chunks_from_ingestion_db(organization_id, source_name, page, page_size)
    except Exception as e:
        LOGGER.exception(
            "Failed to get chunks in database for organization %s, source %s",
            organization_id,
            source_name,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/organizations/{organization_id}/ingestion_database/sources/{source_name}/chunks/{chunk_id}")
def update_chunk_info_in_database(
    organization_id: UUID,
    source_name: str,
    chunk_id: str,
    update_request: UpdateChunk,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
) -> ChunkData:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return update_chunk_info_in_ingestion_db(organization_id, source_name, chunk_id, update_request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception(
            "Failed to update chunk info in database for organization %s, source %s, chunk %s",
            organization_id,
            source_name,
            chunk_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/organizations/{organization_id}/ingestion_database/sources/{source_name}/chunks/{chunk_id}")
def delete_chunks_in_database(
    organization_id: UUID,
    source_name: str,
    chunk_ids: list[str],
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        delete_chunks_from_ingestion_db(organization_id, source_name, chunk_ids)
    except Exception as e:
        LOGGER.error(
            "Failed to delete chunks in database for organization %s, source %s, chunk %s: %s",
            organization_id,
            source_name,
            chunk_ids,
            str(e),
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e

    return Response(status_code=status.HTTP_204_NO_CONTENT)
