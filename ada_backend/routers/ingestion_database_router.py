import logging
from fastapi import APIRouter
from typing import Annotated
from fastapi import Depends, HTTPException
from uuid import UUID

from sqlalchemy.orm import Session

from engine.storage_service.db_utils import DBDefinition
from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    verify_ingestion_api_key_dependency,
    user_has_access_to_organization_dependency,
    UserRights,
    SupabaseUser,
)
from ada_backend.schemas.ingestion_database_schema import (
    ChunkData,
    UpdateChunk,
)
from ada_backend.services.ingestion_database_service import (
    create_table_in_ingestion_db,
    update_chunk_info_in_ingestion_db,
)
from ada_backend.services.errors import SourceNotFound


router = APIRouter(tags=["Ingestion Database"])
LOGGER = logging.getLogger(__name__)


@router.post("/organizations/{organization_id}/ingestion_database")
def create_table_in_database(
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    organization_id: UUID,
    source_id: UUID,
    table_definition: DBDefinition,
) -> tuple[str, DBDefinition]:
    try:
        table_name, table_definition = create_table_in_ingestion_db(organization_id, source_id, table_definition)
        return table_name, table_definition
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.exception(
            "Failed to create table in database for organization %s, source %s",
            organization_id,
            source_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/organizations/{organization_id}/ingestion_database/sources/{source_id}/chunks/{chunk_id}")
def update_chunk_info_in_database(
    organization_id: UUID,
    source_id: UUID,
    chunk_id: str,
    update_request: UpdateChunk,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> ChunkData:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return update_chunk_info_in_ingestion_db(session, source_id, chunk_id, update_request)
    except SourceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception(
            "Failed to update chunk info in database for organization %s, source %s, chunk %s",
            organization_id,
            source_id,
            chunk_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
