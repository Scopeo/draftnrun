import logging
from fastapi import APIRouter
from typing import Annotated
from fastapi import Depends, HTTPException
from uuid import UUID

from engine.storage_service.db_utils import DBDefinition
from ingestion_script.utils import get_sanitize_names
from engine.storage_service.local_service import SQLLocalService
from ada_backend.routers.auth_router import verify_ingestion_api_key_dependency
from settings import settings


router = APIRouter(tags=["Ingestion Database Management"], prefix="/ingestion_database_management")
LOGGER = logging.getLogger(__name__)


@router.post("/organizations/{organization_id}")
def create_table_in_database(
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    organization_id: UUID,
    source_name: str,
    table_definition: DBDefinition,
) -> None:
    try:
        sql_local_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
        schema_name, table_name, qdrant_collection_name = get_sanitize_names(
            source_name=source_name,
            organization_id=str(organization_id),
        )
        sql_local_service.create_table(
            table_name=table_name,
            table_definition=table_definition,
            schema_name=schema_name,
        )
        return None
    except Exception as e:
        LOGGER.exception(
            "Failed to create table in database for organization %s",
            organization_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/organizations/{organization_id}")
def delete_table_in_database(
    verified_ingestion_api_key: Annotated[None, Depends(verify_ingestion_api_key_dependency)],
    organization_id: UUID,
    source_name: str,
) -> None:
    try:
        sql_local_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
        schema_name, table_name, qdrant_collection_name = get_sanitize_names(
            source_name=source_name,
            organization_id=str(organization_id),
        )
        sql_local_service.drop_table(
            table_name=table_name,
            schema_name=schema_name,
        )
        return None
    except Exception as e:
        LOGGER.exception(
            "Failed to delete table in database for organization %s",
            organization_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
