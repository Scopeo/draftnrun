from uuid import UUID

from sqlalchemy.orm import Session

from engine.storage_service.local_service import SQLLocalService
from engine.storage_service.errors import RowNotFoundError
from ada_backend.schemas.ingestion_database_schema import (
    ChunkData,
    UpdateChunk,
)
from ingestion_script.utils import get_sanitize_names, SOURCE_ID_COLUMN_NAME
from engine.storage_service.db_utils import DBDefinition
from settings import settings
from ada_backend.repositories.source_repository import get_data_source_by_id
from ada_backend.services.errors import SourceNotFound, ChunkSourceMismatchError, ChunkNotFoundError


def get_sql_local_service_for_ingestion() -> SQLLocalService:
    return SQLLocalService(engine_url=settings.INGESTION_DB_URL)


def create_table_in_ingestion_db(
    organization_id: UUID,
    source_id: UUID,
    table_definition: DBDefinition,
) -> tuple[str, DBDefinition]:
    sql_local_service = get_sql_local_service_for_ingestion()
    schema_name, table_name, qdrant_collection_name = get_sanitize_names(
        organization_id=str(organization_id),
        embedding_model_reference=None,
    )
    sql_local_service.create_table(
        table_name=table_name,
        table_definition=table_definition,
        schema_name=schema_name,
    )
    return table_name, table_definition


def update_chunk_info_in_ingestion_db(
    session: Session,
    source_id: UUID,
    chunk_id: str,
    update_request: UpdateChunk,
) -> ChunkData:
    sql_local_service = get_sql_local_service_for_ingestion()
    source = get_data_source_by_id(session, source_id)
    if not source:
        raise SourceNotFound(source_id)

    schema_name = source.database_schema
    table_name = source.database_table_name

    try:
        existing_row = sql_local_service.get_row_by_id(
            table_name=table_name,
            schema_name=schema_name,
            chunk_id=chunk_id,
        )
    except RowNotFoundError as e:
        raise ChunkNotFoundError(chunk_id=chunk_id) from e

    if existing_row.get(SOURCE_ID_COLUMN_NAME) != str(source_id):
        raise ChunkSourceMismatchError(chunk_id=chunk_id, source_id=source_id)

    sql_local_service.update_row(
        table_name=table_name,
        schema_name=schema_name,
        chunk_id=chunk_id,
        update_data=update_request.update_data,
        sql_query_filter=f"{SOURCE_ID_COLUMN_NAME} = '{source_id}'",
    )
    updated_row = sql_local_service.get_row_by_id(
        table_name=table_name,
        schema_name=schema_name,
        chunk_id=chunk_id,
    )
    return ChunkData(data=updated_row)
