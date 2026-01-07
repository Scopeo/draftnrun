import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ada_backend.routers.auth_router import verify_ingestion_api_key_dependency
from ada_backend.services.ingestion_database_service import create_table_in_ingestion_db
from engine.storage_service.db_utils import DBDefinition

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
