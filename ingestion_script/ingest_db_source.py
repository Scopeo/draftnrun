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


def _serialize_value(value):
    """Convert Timestamp/datetime objects to ISO format strings for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _infer_qdrant_field_schema(sample_value) -> FieldSchema:
    """Infer Qdrant field schema from a sample Python value."""
    if isinstance(sample_value, (int, float)):
        return FieldSchema.FLOAT
    if isinstance(sample_value, bool):
        return FieldSchema.BOOL
    if isinstance(sample_value, datetime):
        return FieldSchema.DATETIME
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
    source_rows = sql_local_service.get_table_rows(
        table_name=table_name,
        schema_name=source_schema_name,
        sql_query_filter=sql_query_filter,
    )
    if not source_rows:
        raise ValueError(f"The table '{table_name}' is empty. No data to ingest.")

    col_names = set(source_rows[0].keys())
    if id_column_name not in col_names:
        raise ValueError(f"ID column '{id_column_name}' not found in the columns: {sorted(col_names)}")
    if not set(text_column_names).issubset(col_names):
        raise ValueError(f"Text columns {text_column_names} not found in the columns: {sorted(col_names)}")
    if metadata_column_names is not None and not set(metadata_column_names).issubset(col_names):
        raise ValueError(f"Metadata columns {metadata_column_names} not found in the columns: {sorted(col_names)}")
    if timestamp_column_name and timestamp_column_name not in col_names:
        raise ValueError(
            f"Timestamp column '{timestamp_column_name}' not found in the columns: {sorted(col_names)}"
        )

    if metadata_column_names:
        for col in metadata_column_names:
            sample = next((r[col] for r in source_rows if r.get(col) is not None), None)
            field_schema = _infer_qdrant_field_schema(sample)
            LOGGER.info(f"Creating index for metadata column '{col}' with qdrant type {field_schema}")
            await qdrant_service.create_index_if_needed_async(
                collection_name=qdrant_collection_name,
                field_name=col,
                field_schema_type=field_schema,
            )
    if timestamp_column_name:
        await qdrant_service.create_index_if_needed_async(
            collection_name=qdrant_collection_name,
            field_name=timestamp_column_name,
            field_schema_type=FieldSchema.DATETIME,
        )

    LOGGER.info(f"Retrieved {len(source_rows)} rows from the source table '{table_name}'.")

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    unified_rows: list[dict] = []

    for src_row in source_rows:
        row_id = src_row[id_column_name]
        combined_text = " ".join(str(src_row.get(c) or "") for c in text_column_names)
        chunks = splitter.split_text(combined_text)
        file_id = f"{table_name}_{row_id}"
        ts_value = src_row.get(timestamp_column_name) if timestamp_column_name else None

        for idx, chunk_text in enumerate(chunks, start=1):
            chunk_id = f"{row_id}_{idx}"

            if url_pattern:
                safe_row = {k: ("" if v is None else v) for k, v in src_row.items()}
                url_val = url_pattern.format_map(safe_row)
            else:
                url_val = None

            metadata: dict = {}
            if timestamp_column_name and ts_value is not None:
                metadata[timestamp_column_name] = _serialize_value(ts_value)
            if metadata_column_names:
                for mc in metadata_column_names:
                    if mc != timestamp_column_name:
                        mv = src_row.get(mc)
                        if mv is not None:
                            metadata[mc] = _serialize_value(mv)

            unified_rows.append({
                CHUNK_ID_COLUMN_NAME: chunk_id,
                CHUNK_COLUMN_NAME: chunk_text,
                FILE_ID_COLUMN_NAME: file_id,
                ORDER_COLUMN_NAME: idx - 1,
                DOCUMENT_TITLE_COLUMN_NAME: file_id,
                TIMESTAMP_COLUMN_NAME: _serialize_value(ts_value),
                URL_COLUMN_NAME: url_val,
                METADATA_COLUMN_NAME: json.dumps(metadata) if metadata else json.dumps({}),
            })

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

    sid = str(source_id)
    for row in rows:
        row[SOURCE_ID_COLUMN_NAME] = sid

    for i in range(0, len(rows), settings.INGESTION_BATCH_SIZE):
        batch = rows[i : i + settings.INGESTION_BATCH_SIZE]
        LOGGER.info(f"Flushing DB-source batch {i // settings.INGESTION_BATCH_SIZE + 1} ({len(batch)} rows)")
        db_service.update_table(
            new_rows=batch,
            table_name=storage_table_name,
            table_definition=db_definition,
            id_column_name=CHUNK_ID_COLUMN_NAME,
            timestamp_column_name=TIMESTAMP_COLUMN_NAME,
            append_mode=update_existing,
            schema_name=storage_schema_name,
            sql_query_filter=combined_filter_sql_unified,
            source_id=sid,
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
