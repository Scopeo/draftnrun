import json
import logging
from datetime import datetime
from functools import partial
from typing import Optional
from uuid import UUID

from llama_index.core.node_parser import SentenceSplitter

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import SourceAttributes
from engine.qdrant_service import FieldSchema, QdrantService
from engine.storage_service.db_service import DBService
from engine.storage_service.db_utils import DBDefinition
from engine.storage_service.local_service import SQLLocalService
from ingestion_script.ingest_folder_source import (
    TIMESTAMP_COLUMN_NAME,
    sync_chunks_to_qdrant,
)
from ingestion_script.utils import (
    CHUNK_COLUMN_NAME,
    CHUNK_ID_COLUMN_NAME,
    DOCUMENT_TITLE_COLUMN_NAME,
    FILE_ID_COLUMN_NAME,
    METADATA_COLUMN_NAME,
    ORDER_COLUMN_NAME,
    SOURCE_ID_COLUMN_NAME,
    UNIFIED_QDRANT_SCHEMA,
    UNIFIED_TABLE_DEFINITION,
    URL_COLUMN_NAME,
    build_combined_sql_filter,
    map_source_filter_to_unified_table_filter,
    resolve_sql_timestamp_filter,
    upload_source,
)
from settings import settings

LOGGER = logging.getLogger(__name__)


def _map_sqlalchemy_type_to_internal(type_str: str) -> str:
    """
    Map SQLAlchemy/reflected type string to internal type used by DBDefinition/SQLLocalService.
    Falls back to VARCHAR when unknown; prefers DATETIME for date-like types.
    """
    type_upper = type_str.upper()
    if "TIMESTAMP" in type_upper or "DATETIME" in type_upper or type_upper == "DATE":
        return "DATETIME"
    if type_upper.startswith("VARCHAR") or "CHAR" in type_upper:
        return "VARCHAR"
    if "TEXT" in type_upper:
        return "TEXT"
    if "INT" in type_upper:
        return "INTEGER"
    if any(x in type_upper for x in ["DOUBLE", "FLOAT", "NUMERIC", "DECIMAL", "REAL"]):
        return "FLOAT"
    if "BOOL" in type_upper:
        return "BOOLEAN"
    if "JSON" in type_upper or "VARIANT" in type_upper:
        return "VARIANT"
    if "ARRAY" in type_upper:
        return "ARRAY"
    return "VARCHAR"


def _serialize_value(value):
    """Convert Timestamp/datetime objects to ISO format strings for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _infer_qdrant_field_schema_from_sql_type(sql_type: str) -> FieldSchema:
    """Map a SQL column type string to a Qdrant FieldSchema."""
    type_upper = sql_type.upper()
    if "TIMESTAMP" in type_upper or "DATETIME" in type_upper or type_upper == "DATE":
        return FieldSchema.DATETIME
    if "INT" in type_upper:
        return FieldSchema.INTEGER
    if any(x in type_upper for x in ["DOUBLE", "FLOAT", "NUMERIC", "DECIMAL", "REAL"]):
        return FieldSchema.FLOAT
    if "BOOL" in type_upper:
        return FieldSchema.BOOLEAN
    return FieldSchema.KEYWORD


async def get_db_source(
    db_url: str,
    table_name: str,
    id_column_name: str,
    text_column_names: list[str],
    qdrant_service: QdrantService,
    qdrant_collection_name: str,
    source_schema_name: Optional[str] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
    url_pattern: Optional[str] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
    sql_query_filter: Optional[str] = None,
) -> list[dict]:
    sql_local_service = SQLLocalService(engine_url=db_url)

    column_info = sql_local_service.get_column_info(table_name, schema_name=source_schema_name)
    column_names = set(column_info.keys())

    if id_column_name not in column_names:
        raise ValueError(f"ID column '{id_column_name}' not found in the columns: {sorted(column_names)}")
    if not set(text_column_names).issubset(column_names):
        raise ValueError(f"Text columns {text_column_names} not found in the columns: {sorted(column_names)}")
    if metadata_column_names is not None and not set(metadata_column_names).issubset(column_names):
        raise ValueError(
            f"Metadata columns {metadata_column_names} not found in the columns: {sorted(column_names)}"
        )
    if timestamp_column_name and timestamp_column_name not in column_names:
        raise ValueError(
            f"Timestamp column '{timestamp_column_name}' not found in the columns: {sorted(column_names)}"
        )

    if metadata_column_names:
        for metadata_col in metadata_column_names:
            field_schema = _infer_qdrant_field_schema_from_sql_type(column_info.get(metadata_col, "VARCHAR"))
            LOGGER.info(f"Creating index for metadata column '{metadata_col}' with qdrant type {field_schema}")
            await qdrant_service.create_index_if_needed_async(
                collection_name=qdrant_collection_name,
                field_name=metadata_col,
                field_schema_type=field_schema,
            )
    if timestamp_column_name:
        await qdrant_service.create_index_if_needed_async(
            collection_name=qdrant_collection_name,
            field_name=timestamp_column_name,
            field_schema_type=FieldSchema.DATETIME,
        )

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    unified_rows: list[dict] = []
    total_source_rows = 0

    for batch in sql_local_service.iter_table_rows(
        table_name=table_name,
        batch_size=settings.INGESTION_BATCH_SIZE,
        schema_name=source_schema_name,
        sql_query_filter=sql_query_filter,
    ):
        total_source_rows += len(batch)
        for source_row in batch:
            row_id = source_row[id_column_name]
            combined_text = " ".join(str(source_row.get(col) or "") for col in text_column_names)
            chunks = splitter.split_text(combined_text)
            file_id = f"{table_name}_{row_id}"
            timestamp_value = source_row.get(timestamp_column_name) if timestamp_column_name else None

            for chunk_index, chunk_text in enumerate(chunks, start=1):
                chunk_id = f"{row_id}_{chunk_index}"

                if url_pattern:
                    null_safe_row = {k: ("" if v is None else v) for k, v in source_row.items()}
                    url_value = url_pattern.format_map(null_safe_row)
                else:
                    url_value = None

                metadata: dict = {}
                if timestamp_column_name and timestamp_value is not None:
                    metadata[timestamp_column_name] = _serialize_value(timestamp_value)
                if metadata_column_names:
                    for metadata_col_name in metadata_column_names:
                        if metadata_col_name != timestamp_column_name:
                            metadata_value = source_row.get(metadata_col_name)
                            if metadata_value is not None:
                                metadata[metadata_col_name] = _serialize_value(metadata_value)

                unified_rows.append({
                    CHUNK_ID_COLUMN_NAME: chunk_id,
                    CHUNK_COLUMN_NAME: chunk_text,
                    FILE_ID_COLUMN_NAME: file_id,
                    ORDER_COLUMN_NAME: chunk_index - 1,
                    DOCUMENT_TITLE_COLUMN_NAME: file_id,
                    TIMESTAMP_COLUMN_NAME: _serialize_value(timestamp_value),
                    URL_COLUMN_NAME: url_value,
                    METADATA_COLUMN_NAME: json.dumps(metadata) if metadata else json.dumps({}),
                })

    if total_source_rows == 0:
        raise ValueError(f"The table '{table_name}' is empty. No data to ingest.")

    LOGGER.info(f"Retrieved {total_source_rows} rows from the source table '{table_name}'.")
    return unified_rows


async def upload_db_source(
    db_service: DBService,
    qdrant_service: QdrantService,
    db_definition: DBDefinition,
    storage_schema_name: str,
    storage_table_name: str,
    qdrant_collection_name: str,
    source_id: UUID,
    source_db_url: str,
    source_table_name: str,
    id_column_name: str,
    text_column_names: list[str],
    source_schema_name: Optional[str] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
    url_pattern: Optional[str] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
    update_existing: bool = False,
    query_filter: Optional[str] = None,
    timestamp_filter: Optional[str] = None,
):
    resolved_timestamp_filter = resolve_sql_timestamp_filter(timestamp_filter)

    if timestamp_filter and resolved_timestamp_filter:
        LOGGER.info(f"Resolved timestamp filter from '{timestamp_filter}' to '{resolved_timestamp_filter}'")

    combined_filter_sql = build_combined_sql_filter(
        query_filter=query_filter,
        timestamp_filter=resolved_timestamp_filter,
        timestamp_column_name=timestamp_column_name,
    )

    combined_filter_sql_unified = map_source_filter_to_unified_table_filter(
        sql_filter=combined_filter_sql,
        timestamp_column_name=timestamp_column_name,
    )

    combined_filter_qdrant = qdrant_service._build_combined_filter(
        query_filter=query_filter,
        timestamp_filter=resolved_timestamp_filter,
        timestamp_column_name=timestamp_column_name,
    )

    rows = await get_db_source(
        db_url=source_db_url,
        table_name=source_table_name,
        id_column_name=id_column_name,
        text_column_names=text_column_names,
        source_schema_name=source_schema_name,
        metadata_column_names=metadata_column_names,
        timestamp_column_name=timestamp_column_name,
        url_pattern=url_pattern,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        sql_query_filter=combined_filter_sql,
        qdrant_service=qdrant_service,
        qdrant_collection_name=qdrant_collection_name,
    )

    source_id_str = str(source_id)
    incoming_ids: set[str] = set()
    for i in range(0, len(rows), settings.INGESTION_BATCH_SIZE):
        batch = rows[i : i + settings.INGESTION_BATCH_SIZE]
        for row in batch:
            row[SOURCE_ID_COLUMN_NAME] = source_id_str
            incoming_ids.add(row[CHUNK_ID_COLUMN_NAME])
        LOGGER.info(f"Flushing DB-source batch {i // settings.INGESTION_BATCH_SIZE + 1} ({len(batch)} rows)")
        db_service.update_table(
            new_rows=batch,
            table_name=storage_table_name,
            table_definition=db_definition,
            id_column_name=CHUNK_ID_COLUMN_NAME,
            timestamp_column_name=TIMESTAMP_COLUMN_NAME,
            append_mode=True,
            schema_name=storage_schema_name,
            sql_query_filter=combined_filter_sql_unified,
            source_id=source_id_str,
        )

    if not update_existing:
        db_service.delete_stale_rows(
            table_name=storage_table_name,
            id_column_name=CHUNK_ID_COLUMN_NAME,
            incoming_ids=incoming_ids,
            table_definition=db_definition,
            schema_name=storage_schema_name,
            sql_query_filter=combined_filter_sql_unified,
            source_id=source_id_str,
        )

    LOGGER.info(f"Updated table '{storage_table_name}' in schema '{storage_schema_name}' with {len(rows)} rows.")
    await sync_chunks_to_qdrant(
        storage_schema_name,
        storage_table_name,
        collection_name=qdrant_collection_name,
        db_service=db_service,
        qdrant_service=qdrant_service,
        sql_query_filter=combined_filter_sql_unified,  # Use unified filter for sync
        query_filter_qdrant=combined_filter_qdrant,
        source_id=source_id,
    )


async def ingestion_database(
    source_name: str,
    organization_id: str,
    task_id: UUID,
    source_db_url: str,
    source_table_name: str,
    id_column_name: str,
    text_column_names: list[str],
    source_schema_name: Optional[str] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
    url_pattern: Optional[str] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
    update_existing: bool = False,
    query_filter: Optional[str] = None,
    timestamp_filter: Optional[str] = None,
    source_attributes: Optional[SourceAttributes] = None,
    source_id: Optional[UUID] = None,
) -> None:
    source_type = db.SourceType.DATABASE
    LOGGER.info("Start ingestion data from the database source...")
    qdrant_schema = UNIFIED_QDRANT_SCHEMA
    metadata_fields_to_keep = set(metadata_column_names) if metadata_column_names else None
    if metadata_fields_to_keep:
        metadata_field_types = {col: "VARCHAR" for col in metadata_fields_to_keep}
    if timestamp_column_name:
        metadata_fields_to_keep.add(timestamp_column_name)
        metadata_field_types[timestamp_column_name] = "DATETIME"
    qdrant_schema.metadata_fields_to_keep = metadata_fields_to_keep
    qdrant_schema.metadata_field_types = metadata_field_types if metadata_field_types else None
    await upload_source(
        source_name,
        organization_id,
        task_id,
        source_type,
        qdrant_schema,
        update_existing=update_existing,
        ingestion_function=partial(
            upload_db_source,
            db_definition=UNIFIED_TABLE_DEFINITION,
            source_db_url=source_db_url,
            source_schema_name=source_schema_name,
            source_table_name=source_table_name,
            id_column_name=id_column_name,
            text_column_names=text_column_names,
            metadata_column_names=metadata_column_names,
            timestamp_column_name=timestamp_column_name,
            url_pattern=url_pattern,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            query_filter=query_filter,
            timestamp_filter=timestamp_filter,
        ),
        attributes=source_attributes,
        source_id=source_id,
    )
