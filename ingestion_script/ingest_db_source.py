import json
import logging
from collections.abc import AsyncGenerator
from datetime import date, datetime
from decimal import Decimal
from functools import partial
from typing import Any, Optional
from uuid import UUID

from llama_index.core.node_parser import SentenceSplitter

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import SourceAttributes
from engine.datetime_utils import make_naive_utc, parse_datetime
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
from settings import settings

LOGGER = logging.getLogger(__name__)


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


def _build_source_filter(source_id: str, sql_query_filter: Optional[str]) -> str:
    source_scope_filter = f"{SOURCE_ID_COLUMN_NAME} = '{source_id}'"
    if sql_query_filter:
        return f"({sql_query_filter}) AND ({source_scope_filter})"
    return source_scope_filter


def _is_source_row_newer(source_timestamp, existing_timestamp) -> bool:
    incoming_dt = parse_datetime(source_timestamp)
    existing_dt = parse_datetime(existing_timestamp)

    if incoming_dt is not None and existing_dt is not None:
        return make_naive_utc(incoming_dt) > make_naive_utc(existing_dt)

    return _serialize_value(source_timestamp) != _serialize_value(existing_timestamp)


def _iter_batches(items: list[Any], batch_size: int):
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


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
    include_row_ids: Optional[set[Any]] = None,
) -> AsyncGenerator[list[dict], None]:
    sql_local_service = SQLLocalService(engine_url=db_url)

    column_info = sql_local_service.get_column_info(table_name, schema_name=source_schema_name)
    column_names = set(column_info.keys())

    if id_column_name not in column_names:
        raise ValueError(f"ID column '{id_column_name}' not found in the columns: {sorted(column_names)}")
    if not set(text_column_names).issubset(column_names):
        raise ValueError(f"Text columns {text_column_names} not found in the columns: {sorted(column_names)}")
    if metadata_column_names is not None and not set(metadata_column_names).issubset(column_names):
        raise ValueError(f"Metadata columns {metadata_column_names} not found in the columns: {sorted(column_names)}")
    if timestamp_column_name and timestamp_column_name not in column_names:
        raise ValueError(
            f"Timestamp column '{timestamp_column_name}' not found in the columns: {sorted(column_names)}"
        )

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

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    if include_row_ids is not None:
        source_batches = (
            sql_local_service.get_rows_by_ids(
                table_name=table_name,
                chunk_ids=id_batch,
                schema_name=source_schema_name,
                id_column_name=id_column_name,
                sql_query_filter=sql_query_filter,
            )
            for id_batch in _iter_batches(list(include_row_ids), settings.INGESTION_BATCH_SIZE)
        )
    else:
        source_batches = sql_local_service.iter_table_rows(
            table_name=table_name,
            schema_name=source_schema_name,
            sql_query_filter=sql_query_filter,
        )

    for batch in source_batches:
        batch_rows: list[dict] = []
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

                batch_rows.append({
                    CHUNK_ID_COLUMN_NAME: chunk_id,
                    CHUNK_COLUMN_NAME: chunk_text,
                    FILE_ID_COLUMN_NAME: file_id,
                    ORDER_COLUMN_NAME: chunk_index - 1,
                    DOCUMENT_TITLE_COLUMN_NAME: file_id,
                    TIMESTAMP_COLUMN_NAME: _serialize_value(timestamp_value),
                    URL_COLUMN_NAME: url_value,
                    METADATA_COLUMN_NAME: json.dumps(metadata) if metadata else json.dumps({}),
                })
        if batch_rows:
            yield batch_rows


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

    source_id_str = str(source_id)
    sql_local_service = SQLLocalService(engine_url=source_db_url)
    source_columns = [id_column_name]
    if timestamp_column_name:
        source_columns.append(timestamp_column_name)
    source_id_timestamp_rows = sql_local_service.get_column_values(
        table_name=source_table_name,
        columns=source_columns,
        schema_name=source_schema_name,
        sql_query_filter=combined_filter_sql,
    )
    if not source_id_timestamp_rows:
        raise ValueError(f"The table '{source_table_name}' is empty. No data to ingest.")

    row_ids_to_process: set[Any] = set()
    incoming_file_ids: set[str] = set()
    incoming_timestamp_by_file_id: dict[str, Optional[str]] = {}
    for source_row in source_id_timestamp_rows:
        file_id = f"{source_table_name}_{source_row[id_column_name]}"
        incoming_file_ids.add(file_id)
        timestamp_value = source_row.get(timestamp_column_name) if timestamp_column_name else None
        incoming_timestamp_by_file_id[file_id] = _serialize_value(timestamp_value)

    scoped_unified_filter = _build_source_filter(
        source_id=source_id_str,
        sql_query_filter=combined_filter_sql_unified,
    )
    existing_unified_rows = db_service.get_column_values(
        table_name=storage_table_name,
        columns=[CHUNK_ID_COLUMN_NAME, FILE_ID_COLUMN_NAME, TIMESTAMP_COLUMN_NAME],
        schema_name=storage_schema_name,
        sql_query_filter=scoped_unified_filter,
    )
    existing_timestamp_by_file_id: dict[str, Optional[str]] = {}
    existing_chunk_ids_by_file_id: dict[str, set[str]] = {}
    for unified_row in existing_unified_rows:
        unified_file_id = unified_row[FILE_ID_COLUMN_NAME]
        unified_chunk_id = unified_row[CHUNK_ID_COLUMN_NAME]
        existing_chunk_ids_by_file_id.setdefault(unified_file_id, set()).add(unified_chunk_id)
        if unified_file_id not in existing_timestamp_by_file_id:
            existing_timestamp_by_file_id[unified_file_id] = _serialize_value(
                unified_row.get(TIMESTAMP_COLUMN_NAME)
            )

    existing_file_ids = set(existing_chunk_ids_by_file_id.keys())
    new_file_ids = incoming_file_ids - existing_file_ids
    deleted_file_ids = existing_file_ids - incoming_file_ids
    common_file_ids = incoming_file_ids & existing_file_ids

    if timestamp_column_name:
        updated_file_ids = {
            file_id for file_id in common_file_ids
            if _is_source_row_newer(
                incoming_timestamp_by_file_id[file_id],
                existing_timestamp_by_file_id[file_id],
            )
        }
    else:
        updated_file_ids = common_file_ids

    changed_file_ids = new_file_ids | updated_file_ids
    file_id_prefix = f"{source_table_name}_"
    for file_id in changed_file_ids:
        row_ids_to_process.add(file_id.removeprefix(file_id_prefix))

    chunks_to_delete_for_update: set[str] = set()
    for file_id in updated_file_ids:
        chunks_to_delete_for_update.update(existing_chunk_ids_by_file_id.get(file_id, set()))

    chunks_to_delete_for_stale: set[str] = set()
    if not update_existing:
        for file_id in deleted_file_ids:
            chunks_to_delete_for_stale.update(existing_chunk_ids_by_file_id.get(file_id, set()))

    chunk_ids_to_delete = chunks_to_delete_for_update | chunks_to_delete_for_stale
    if chunk_ids_to_delete:
        db_service.delete_rows_from_table(
            table_name=storage_table_name,
            ids=list(chunk_ids_to_delete),
            schema_name=storage_schema_name,
            id_column_name=CHUNK_ID_COLUMN_NAME,
        )

    total_rows = 0
    batch_number = 0

    async for chunk_batch in get_db_source(
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
        include_row_ids=row_ids_to_process,
        qdrant_service=qdrant_service,
        qdrant_collection_name=qdrant_collection_name,
    ):
        batch_number += 1
        for row in chunk_batch:
            row[SOURCE_ID_COLUMN_NAME] = source_id_str
        total_rows += len(chunk_batch)
        LOGGER.info(f"Flushing DB-source batch {batch_number} ({len(chunk_batch)} rows)")
        db_service.update_table(
            new_rows=chunk_batch,
            table_name=storage_table_name,
            table_definition=db_definition,
            id_column_name=CHUNK_ID_COLUMN_NAME,
            timestamp_column_name=TIMESTAMP_COLUMN_NAME,
            append_mode=True,
            schema_name=storage_schema_name,
            sql_query_filter=combined_filter_sql_unified,
            source_id=source_id_str,
        )

    LOGGER.info(f"Updated table '{storage_table_name}' in schema '{storage_schema_name}' with {total_rows} rows.")
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
