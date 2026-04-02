import json
import logging
from datetime import date, datetime
from decimal import Decimal
from functools import partial
from typing import Optional
from uuid import UUID

from llama_index.core.node_parser import SentenceSplitter

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import SourceAttributes
from engine.qdrant_service import FieldSchema, QdrantService, map_sql_type_to_qdrant_field_schema
from engine.storage_service.db_service import DBService
from engine.storage_service.db_utils import DBDefinition
from engine.storage_service.local_service import SQLLocalService
from ingestion_script.ingest_folder_source import TIMESTAMP_COLUMN_NAME, sync_chunks_to_qdrant
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


def build_file_id(table_name: str, row_id) -> str:
    return f"{table_name}_{row_id}"


def extract_row_id_from_file_id(file_id: str, table_name: str) -> str:
    prefix = f"{table_name}_"
    return file_id[len(prefix) :]


def _serialize_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return value


def _validate_source_columns(
    sql_local_service: SQLLocalService,
    table_name: str,
    id_column_name: str,
    source_schema_name: Optional[str],
    text_column_names: Optional[list[str]] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
) -> dict:
    column_info = sql_local_service.get_column_info(table_name, schema_name=source_schema_name)
    column_names = set(column_info.keys())

    if id_column_name not in column_names:
        raise ValueError(f"ID column '{id_column_name}' not found in the columns: {sorted(column_names)}")
    if text_column_names and not set(text_column_names).issubset(column_names):
        raise ValueError(f"Text columns {text_column_names} not found in the columns: {sorted(column_names)}")
    if metadata_column_names is not None and not set(metadata_column_names).issubset(column_names):
        raise ValueError(f"Metadata columns {metadata_column_names} not found in the columns: {sorted(column_names)}")
    if timestamp_column_name and timestamp_column_name not in column_names:
        raise ValueError(
            f"Timestamp column '{timestamp_column_name}' not found in the columns: {sorted(column_names)}"
        )
    return column_info


def get_db_source_ids(
    table_name: str,
    id_column_name: str,
    sql_local_service: SQLLocalService,
    source_schema_name: Optional[str] = None,
    timestamp_column_name: Optional[str] = None,
    sql_query_filter: Optional[str] = None,
) -> dict[str, any]:
    _validate_source_columns(
        sql_local_service,
        table_name,
        id_column_name,
        source_schema_name,
        timestamp_column_name=timestamp_column_name,
    )

    columns = [id_column_name]
    if timestamp_column_name:
        columns.append(timestamp_column_name)

    id_timestamp_data = sql_local_service.fetch_selected_columns(
        table_name=table_name,
        columns=columns,
        schema_name=source_schema_name,
        sql_query_filter=sql_query_filter,
    )
    # TODO: Have a sync_id column in the source table and use it to track the sync progress
    return {
        build_file_id(table_name, row[id_column_name]): _serialize_value(row.get(timestamp_column_name))
        if timestamp_column_name
        else None
        for row in id_timestamp_data
    }


def fetch_db_source_chunks(
    file_ids: set[str],
    sql_local_service: SQLLocalService,
    table_name: str,
    id_column_name: str,
    text_column_names: list[str],
    source_id: Optional[str] = None,
    source_schema_name: Optional[str] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
    url_pattern: Optional[str] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
) -> list[dict]:
    if not file_ids:
        return []

    raw_row_ids = [extract_row_id_from_file_id(file_id, table_name) for file_id in file_ids]
    id_filter = f"{id_column_name} IN ({','.join(repr(str(raw_id)) for raw_id in raw_row_ids)})"

    source_rows = sql_local_service.get_table_rows(
        table_name=table_name,
        schema_name=source_schema_name,
        sql_query_filter=id_filter,
    )

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    all_chunks: list[dict] = []

    for source_row in source_rows:
        row_id = source_row[id_column_name]
        combined_text = " ".join(str(source_row.get(col) or "") for col in text_column_names)
        chunks = splitter.split_text(combined_text)
        file_id = build_file_id(table_name, row_id)
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

            all_chunks.append({
                CHUNK_ID_COLUMN_NAME: chunk_id,
                CHUNK_COLUMN_NAME: chunk_text,
                FILE_ID_COLUMN_NAME: file_id,
                ORDER_COLUMN_NAME: chunk_index - 1,
                DOCUMENT_TITLE_COLUMN_NAME: file_id,
                TIMESTAMP_COLUMN_NAME: _serialize_value(timestamp_value),
                URL_COLUMN_NAME: url_value,
                METADATA_COLUMN_NAME: json.dumps(metadata) if metadata else json.dumps({}),
                **(({SOURCE_ID_COLUMN_NAME: source_id}) if source_id else {}),
            })

    return all_chunks


async def _ensure_qdrant_indexes(
    qdrant_service: QdrantService,
    qdrant_collection_name: str,
    column_info: dict,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
) -> None:
    if metadata_column_names:
        for metadata_col in metadata_column_names:
            qdrant_field_schema = map_sql_type_to_qdrant_field_schema(column_info.get(metadata_col, "VARCHAR"))
            LOGGER.info(f"Creating index for metadata column '{metadata_col}' with qdrant type {qdrant_field_schema}")
            await qdrant_service.create_index_if_needed_async(
                collection_name=qdrant_collection_name,
                field_name=metadata_col,
                field_schema_type=qdrant_field_schema,
            )
    if timestamp_column_name:
        await qdrant_service.create_index_if_needed_async(
            collection_name=qdrant_collection_name,
            field_name=timestamp_column_name,
            field_schema_type=FieldSchema.DATETIME,
        )


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
    ingestion_id: Optional[str] = None,
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

    source_id_str = str(source_id)

    with SQLLocalService(engine_url=source_db_url) as sql_local_service:
        column_info = _validate_source_columns(
            sql_local_service,
            source_table_name,
            id_column_name,
            source_schema_name,
            text_column_names=text_column_names,
            metadata_column_names=metadata_column_names,
            timestamp_column_name=timestamp_column_name,
        )
        await _ensure_qdrant_indexes(
            qdrant_service,
            qdrant_collection_name,
            column_info,
            metadata_column_names=metadata_column_names,
            timestamp_column_name=timestamp_column_name,
        )

        ids_with_ts = get_db_source_ids(
            table_name=source_table_name,
            id_column_name=id_column_name,
            sql_local_service=sql_local_service,
            source_schema_name=source_schema_name,
            timestamp_column_name=timestamp_column_name,
            sql_query_filter=combined_filter_sql,
        )

        if not ids_with_ts:
            raise ValueError(f"The table '{source_table_name}' is empty. No data to ingest.")

        LOGGER.info(
            "upload_db_source ingestion_id=%s found %d source rows from table %s",
            ingestion_id,
            len(ids_with_ts),
            source_table_name,
        )

        db_service.update_table(
            incoming_ids_with_timestamp=ids_with_ts,
            fetch_rows_fn=partial(
                fetch_db_source_chunks,
                sql_local_service=sql_local_service,
                table_name=source_table_name,
                id_column_name=id_column_name,
                text_column_names=text_column_names,
                source_id=source_id_str,
                source_schema_name=source_schema_name,
                metadata_column_names=metadata_column_names,
                timestamp_column_name=timestamp_column_name,
                url_pattern=url_pattern,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
            table_name=storage_table_name,
            table_definition=db_definition,
            id_column_name=FILE_ID_COLUMN_NAME,
            timestamp_column_name=TIMESTAMP_COLUMN_NAME,
            append_mode=update_existing,
            schema_name=storage_schema_name,
            source_id=source_id_str,
            sql_query_filter=combined_filter_sql_unified,
        )

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
    metadata_fields_to_keep: set[str] = set(metadata_column_names) if metadata_column_names else set()
    metadata_field_types: dict[str, str] = {col: "VARCHAR" for col in metadata_fields_to_keep}
    if timestamp_column_name:
        metadata_fields_to_keep.add(timestamp_column_name)
        metadata_field_types[timestamp_column_name] = "DATETIME"
    qdrant_schema.metadata_fields_to_keep = metadata_fields_to_keep or None
    qdrant_schema.metadata_field_types = metadata_field_types or None
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
