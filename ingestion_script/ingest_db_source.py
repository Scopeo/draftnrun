import json
import logging
import os
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

LOGGER = logging.getLogger(__name__)

DB_INGESTION_BATCH_SIZE = int(os.getenv("DB_INGESTION_BATCH_SIZE", "100"))


def _map_sqlalchemy_type_to_internal(type_str: str) -> str:
    """
    Map SQLAlchemy/reflected type string to internal type used by DBDefinition/SQLLocalService.
    Falls back to VARCHAR when unknown; prefers DATETIME for date-like types.
    """
    t = type_str.upper()
    if "TIMESTAMP" in t or "DATETIME" in t or t == "DATE":
        return "DATETIME"
    if t.startswith("VARCHAR") or "CHAR" in t:
        return "VARCHAR"
    if "TEXT" in t:
        return "TEXT"
    if "INT" in t:
        return "INTEGER"
    if any(x in t for x in ["DOUBLE", "FLOAT", "NUMERIC", "DECIMAL", "REAL"]):
        return "FLOAT"
    if "BOOL" in t:
        return "BOOLEAN"
    if "JSON" in t or "VARIANT" in t:
        return "VARIANT"
    if "ARRAY" in t:
        return "ARRAY"
    return "VARCHAR"


def _map_python_type_to_qdrant(value) -> FieldSchema:
    """Map a Python value to Qdrant FieldSchema for index creation."""
    if isinstance(value, bool):
        return FieldSchema.BOOLEAN
    if isinstance(value, int):
        return FieldSchema.INTEGER
    if isinstance(value, float):
        return FieldSchema.FLOAT
    if isinstance(value, datetime):
        return FieldSchema.DATETIME
    return FieldSchema.KEYWORD


def _serialize_value(value):
    """Convert datetime objects to ISO format strings for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _build_metadata_for_row(
    row: dict,
    timestamp_column_name: Optional[str],
    metadata_column_names: Optional[list[str]],
) -> str:
    """Build JSON metadata string from a row dict."""
    metadata = {}
    if timestamp_column_name:
        timestamp_value = row.get(timestamp_column_name)
        if timestamp_value is not None:
            metadata[timestamp_column_name] = _serialize_value(timestamp_value)
    if metadata_column_names:
        for col in metadata_column_names:
            if col != timestamp_column_name:
                col_value = row.get(col)
                if col_value is not None:
                    metadata[col] = _serialize_value(col_value)
    return json.dumps(metadata)


def _process_row_to_chunks(
    row: dict,
    table_name: str,
    id_column_name: str,
    text_column_names: list[str],
    splitter: SentenceSplitter,
    timestamp_column_name: Optional[str],
    metadata_column_names: Optional[list[str]],
    url_pattern: Optional[str],
    source_id: str,
) -> list[dict]:
    """Process a single source row into a list of unified chunk dicts."""
    # Concatenate text columns
    text_parts = []
    for col in text_column_names:
        val = row.get(col)
        text_parts.append(str(val) if val is not None else "")
    combined_text = " ".join(text_parts)

    # Split into chunks
    chunks = splitter.split_text(combined_text)
    row_id = str(row[id_column_name])
    file_id = f"{table_name}_{row_id}"

    # Build metadata once per row (same for all chunks)
    metadata_json = _build_metadata_for_row(row, timestamp_column_name, metadata_column_names)

    # Timestamp value
    timestamp_value = None
    if timestamp_column_name:
        ts = row.get(timestamp_column_name)
        if ts is not None:
            timestamp_value = _serialize_value(ts)

    # URL value
    url_value = None
    if url_pattern:
        safe_row = {k: ("" if v is None else v) for k, v in row.items()}
        try:
            url_value = url_pattern.format_map(safe_row)
        except (KeyError, IndexError):
            url_value = None

    chunk_dicts = []
    for i, chunk_text in enumerate(chunks):
        chunk_index = i + 1
        chunk_dicts.append({
            CHUNK_ID_COLUMN_NAME: f"{row_id}_{chunk_index}",
            SOURCE_ID_COLUMN_NAME: source_id,
            ORDER_COLUMN_NAME: i,
            FILE_ID_COLUMN_NAME: file_id,
            DOCUMENT_TITLE_COLUMN_NAME: file_id,
            URL_COLUMN_NAME: url_value,
            CHUNK_COLUMN_NAME: chunk_text,
            TIMESTAMP_COLUMN_NAME: timestamp_value,
            METADATA_COLUMN_NAME: metadata_json,
        })

    return chunk_dicts


async def get_db_source(
    db_url: str,
    table_name: str,
    id_column_name: str,
    text_column_names: list[str],
    db_service: DBService,
    storage_table_name: str,
    storage_schema_name: str,
    db_definition: DBDefinition,
    source_id: UUID,
    qdrant_service: QdrantService,
    qdrant_collection_name: str,
    source_schema_name: Optional[str] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
    url_pattern: Optional[str] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
    sql_query_filter: Optional[str] = None,
) -> int:
    """
    Fetch rows from source DB in batches, chunk them, and store to the storage DB.
    Returns total row count processed.
    """
    sql_local_service = SQLLocalService(engine_url=db_url)

    # Validate columns using column info (no full table load)
    column_info = sql_local_service.get_column_info(table_name, schema_name=source_schema_name)
    available_columns = set(column_info.keys())

    if id_column_name not in available_columns:
        raise ValueError(f"ID column '{id_column_name}' not found in the columns: {sorted(available_columns)}")
    if not set(text_column_names).issubset(available_columns):
        raise ValueError(f"Text columns {text_column_names} not found in the columns: {sorted(available_columns)}")
    if metadata_column_names is not None and not set(metadata_column_names).issubset(available_columns):
        raise ValueError(
            f"Metadata columns {metadata_column_names} not found in the columns: {sorted(available_columns)}"
        )
    if timestamp_column_name and timestamp_column_name not in available_columns:
        raise ValueError(
            f"Timestamp column '{timestamp_column_name}' not found in the columns: {sorted(available_columns)}"
        )

    # Create Qdrant indexes based on column types (no pandas needed)
    if metadata_column_names:
        for col in metadata_column_names:
            # Use SQL type info to determine Qdrant field schema
            sql_type = column_info.get(col, "VARCHAR")
            internal_type = _map_sqlalchemy_type_to_internal(sql_type)
            from engine.qdrant_service import map_internal_type_to_qdrant_field_schema

            qdrant_field_schema = map_internal_type_to_qdrant_field_schema(internal_type)
            LOGGER.info(
                f"Creating index for metadata column '{col}' with SQL type {sql_type} "
                f"and qdrant type {qdrant_field_schema}"
            )
            await qdrant_service.create_index_if_needed_async(
                collection_name=qdrant_collection_name,
                field_name=col,
                field_schema_type=qdrant_field_schema,
            )
    if timestamp_column_name:
        await qdrant_service.create_index_if_needed_async(
            collection_name=qdrant_collection_name,
            field_name=timestamp_column_name,
            field_schema_type=FieldSchema.DATETIME,
        )

    # Ensure storage table exists
    if not db_service.table_exists(storage_table_name, schema_name=storage_schema_name):
        db_service.create_table(
            table_name=storage_table_name,
            table_definition=db_definition,
            schema_name=storage_schema_name,
        )

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    source_id_str = str(source_id)
    total_rows = 0

    for batch in sql_local_service.iter_table_rows(
        table_name=table_name,
        batch_size=DB_INGESTION_BATCH_SIZE,
        schema_name=source_schema_name,
        sql_query_filter=sql_query_filter,
    ):
        if not batch:
            break

        total_rows += len(batch)
        batch_chunks = []

        for row in batch:
            row_chunks = _process_row_to_chunks(
                row=row,
                table_name=table_name,
                id_column_name=id_column_name,
                text_column_names=text_column_names,
                splitter=splitter,
                timestamp_column_name=timestamp_column_name,
                metadata_column_names=metadata_column_names,
                url_pattern=url_pattern,
                source_id=source_id_str,
            )
            batch_chunks.extend(row_chunks)

        if batch_chunks:
            db_service.upsert_rows(
                table_name=storage_table_name,
                rows=batch_chunks,
                schema_name=storage_schema_name,
                id_column_names=[CHUNK_ID_COLUMN_NAME, SOURCE_ID_COLUMN_NAME],
            )
            LOGGER.info(
                f"Batch stored: {len(batch)} rows -> {len(batch_chunks)} chunks "
                f"(total rows so far: {total_rows})"
            )

    if total_rows == 0:
        raise ValueError(f"The table '{table_name}' is empty. No data to ingest.")

    LOGGER.info(f"Finished processing {total_rows} rows from source table '{table_name}'.")
    return total_rows


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

    total_rows = await get_db_source(
        db_url=source_db_url,
        table_name=source_table_name,
        id_column_name=id_column_name,
        text_column_names=text_column_names,
        db_service=db_service,
        storage_table_name=storage_table_name,
        storage_schema_name=storage_schema_name,
        db_definition=db_definition,
        source_id=source_id,
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

    LOGGER.info(f"Stored {total_rows} rows to '{storage_table_name}' in schema '{storage_schema_name}'.")

    await sync_chunks_to_qdrant(
        storage_schema_name,
        storage_table_name,
        collection_name=qdrant_collection_name,
        db_service=db_service,
        qdrant_service=qdrant_service,
        sql_query_filter=combined_filter_sql_unified,
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
