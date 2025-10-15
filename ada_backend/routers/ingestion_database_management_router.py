import logging
from fastapi import APIRouter
from typing import Annotated
from fastapi import Depends, HTTPException
from uuid import UUID

from engine.storage_service.db_utils import DBDefinition
from ingestion_script.utils import get_sanitize_names
from ada_backend.routers.auth_router import (
    verify_ingestion_api_key_dependency,
    user_has_access_to_organization_dependency,
    UserRights,
    SupabaseUser,
)
from ada_backend.schemas.ingestion_database_management_schema import RowInfo, UpdateRowRequest
from ada_backend.services.ingestion_database_management_service import get_sql_local_service_for_ingestion


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
        sql_local_service = get_sql_local_service_for_ingestion()
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


@router.get("/organizations/{organization_id}/sources/{source_name}/rows")
def get_rows_in_database(
    organization_id: UUID,
    source_name: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
) -> list[RowInfo]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        sql_local_service = get_sql_local_service_for_ingestion()
        schema_name, table_name, qdrant_collection_name = get_sanitize_names(
            source_name=source_name,
            organization_id=str(organization_id),
        )
        df = sql_local_service.get_table_df(
            table_name=table_name,
            schema_name=schema_name,
        )
        # Convert DataFrame rows to RowInfo objects
        # Use DataFrame index as row_id and convert the entire row to a dict for data
        result = []
        for index, row in df.iterrows():
            row_dict = row.to_dict()
            result.append(RowInfo(row_id=index, data=row_dict, exists=True))
        return result
    except Exception as e:
        LOGGER.exception(
            "Failed to get rows in database for organization %s, source %s",
            organization_id,
            source_name,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/organizations/{organization_id}/sources/{source_name}/rows/{chunk_id}")
def update_row_in_database(
    organization_id: UUID,
    source_name: str,
    chunk_id: str,
    update_request: UpdateRowRequest,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
) -> dict:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        sql_local_service = get_sql_local_service_for_ingestion()
        schema_name, table_name, qdrant_collection_name = get_sanitize_names(
            source_name=source_name,
            organization_id=str(organization_id),
        )

        sql_local_service.update_row(
            table_name=table_name,
            schema_name=schema_name,
            chunk_id=chunk_id,
            update_data=update_request.update_data,
            id_column_name=update_request.id_column_name,
        )
        updated_row = sql_local_service.get_row_by_chunk_id(
            table_name=table_name,
            schema_name=schema_name,
            chunk_id=chunk_id,
            id_column_name=update_request.id_column_name,
        )
        return updated_row
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception(
            "Failed to update row in database for organization %s, source %s, chunk %s",
            organization_id,
            source_name,
            chunk_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/organizations/{organization_id}/sources/{source_name}/rows/{chunk_id}")
def delete_row_in_database(
    organization_id: UUID,
    source_name: str,
    chunk_ids: list[str],
    id_column_name: str,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
) -> None:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        sql_local_service = get_sql_local_service_for_ingestion()
        schema_name, table_name, qdrant_collection_name = get_sanitize_names(
            source_name=source_name,
            organization_id=str(organization_id),
        )
        sql_local_service.delete_rows_from_table(
            table_name=table_name,
            ids=chunk_ids,
            id_column_name=id_column_name,
            schema_name=schema_name,
        )
        return None
    except Exception as e:
        LOGGER.exception(
            "Failed to delete rows in database for organization %s, source %s, chunk %s",
            organization_id,
            source_name,
            chunk_ids,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
