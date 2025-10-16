from uuid import UUID

from engine.storage_service.local_service import SQLLocalService
from ada_backend.schemas.ingestion_database_schema import (
    PaginatedChunkDataResponse,
    ChunkData,
    UpdateChunk,
)
from ingestion_script.utils import get_sanitize_names
from engine.storage_service.db_utils import DBDefinition
from settings import settings


def get_sql_local_service_for_ingestion() -> SQLLocalService:
    return SQLLocalService(engine_url=settings.INGESTION_DB_URL)


def create_table_in_ingestion_db(
    organization_id: UUID,
    source_name: str,
    table_definition: DBDefinition,
) -> tuple[str, DBDefinition]:
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
    return table_name, table_definition


def get_paginated_chunks_from_ingestion_db(
    organization_id: UUID,
    source_name: str,
    page: int,
    page_size: int,
) -> PaginatedChunkDataResponse:
    sql_local_service = get_sql_local_service_for_ingestion()
    schema_name, table_name, qdrant_collection_name = get_sanitize_names(
        source_name=source_name,
        organization_id=str(organization_id),
    )
    rows, total_count = sql_local_service.get_rows_paginated(table_name, schema_name, page, page_size)
    items = []
    for row_dict in rows:
        items.append(ChunkData(data=row_dict))
    total_pages = (total_count + page_size - 1) // page_size
    return PaginatedChunkDataResponse(
        items=items, total=total_count, page=page, page_size=page_size, total_pages=total_pages
    )


def update_chunk_info_in_ingestion_db(
    organization_id: UUID,
    source_name: str,
    chunk_id: str,
    update_request: UpdateChunk,
) -> ChunkData:
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
    )
    updated_row = sql_local_service.get_row_by_chunk_id(
        table_name=table_name,
        schema_name=schema_name,
        chunk_id=chunk_id,
    )
    return ChunkData(data=updated_row)


def delete_chunks_from_ingestion_db(
    organization_id: UUID,
    source_name: str,
    chunk_ids: list[str],
) -> None:
    sql_local_service = get_sql_local_service_for_ingestion()
    schema_name, table_name, qdrant_collection_name = get_sanitize_names(
        source_name=source_name,
        organization_id=str(organization_id),
    )
    sql_local_service.delete_rows_from_table(
        table_name=table_name,
        schema_name=schema_name,
        ids=chunk_ids,
    )
    return None
