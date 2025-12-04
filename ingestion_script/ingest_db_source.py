from functools import partial
import logging
import uuid
from typing import Optional

import pandas as pd
from sqlalchemy import UUID
from llama_index.core.node_parser import SentenceSplitter

from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.storage_service.db_service import DBService
from engine.storage_service.db_utils import (
    PROCESSED_DATETIME_FIELD,
    DBColumn,
    DBDefinition,
)
from engine.storage_service.local_service import SQLLocalService
from ingestion_script.ingest_folder_source import sync_chunks_to_qdrant
from ada_backend.database import models as db
from ingestion_script.utils import (
    upload_source,
    build_combined_sql_filter,
    CHUNK_ID_COLUMN_NAME,
    CHUNK_COLUMN_NAME,
    FILE_ID_COLUMN_NAME,
    URL_COLUMN_NAME,
    ORDER_COLUMN_NAME,
    resolve_sql_timestamp_filter,
)
from ada_backend.schemas.ingestion_task_schema import SourceAttributes

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


def _get_source_column_type_map(
    db_url: str,
    table_name: str,
    schema_name: Optional[str] = None,
) -> dict[str, str]:
    sql_local_service = SQLLocalService(engine_url=db_url)
    description = sql_local_service.describe_table(table_name=table_name, schema_name=schema_name)
    return {row["name"].lower(): _map_sqlalchemy_type_to_internal(str(row["type"])) for row in description}


def get_db_source_definition(
    timestamp_column_name: Optional[str] = None,
    url_pattern: Optional[str] = None,
    metadata_column_names: Optional[list] = None,
    source_db_url: Optional[str] = None,
    source_table_name: Optional[str] = None,
    source_schema_name: Optional[str] = None,
) -> tuple[DBDefinition, dict[str, str]]:
    columns = [
        DBColumn(name=PROCESSED_DATETIME_FIELD, type="DATETIME", default="CURRENT_TIMESTAMP"),
        DBColumn(name=CHUNK_ID_COLUMN_NAME, type="VARCHAR", is_primary_key=True),
        DBColumn(name=FILE_ID_COLUMN_NAME, type="VARCHAR"),
        DBColumn(name=ORDER_COLUMN_NAME, type="INTEGER", is_nullable=True),
        DBColumn(name=CHUNK_COLUMN_NAME, type="VARCHAR"),
    ]
    source_type_map: dict[str, str] = {}
    if source_db_url and source_table_name:
        try:
            source_type_map = _get_source_column_type_map(
                db_url=source_db_url,
                table_name=source_table_name,
                schema_name=source_schema_name,
            )
        except Exception:
            LOGGER.warning("Failed to introspect source table types; falling back to defaults")
            source_type_map = {}

    if timestamp_column_name:
        columns.append(
            DBColumn(
                name=timestamp_column_name,
                type=source_type_map.get(timestamp_column_name.lower()) if source_type_map else "DATETIME",
            )
        )

    if metadata_column_names:
        existing_names = {c.name for c in columns}
        columns.extend(
            DBColumn(
                name=col,
                type=(source_type_map.get(col.lower(), "VARCHAR") if source_type_map else "VARCHAR"),
            )
            for col in metadata_column_names
            if col not in existing_names
        )
    if url_pattern:
        columns.append(DBColumn(name=URL_COLUMN_NAME, type="VARCHAR"))

    return (
        DBDefinition(
            columns=columns,
        ),
        source_type_map,
    )


def get_db_source(
    db_url: str,
    table_name: str,
    id_column_name: str,
    text_column_names: list[str],
    source_schema_name: Optional[str] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
    url_pattern: Optional[str] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
    sql_query_filter: Optional[str] = None,
) -> pd.DataFrame:
    sql_local_service = SQLLocalService(engine_url=db_url)
    df = sql_local_service.get_table_df(
        table_name=table_name,
        schema_name=source_schema_name,
        sql_query_filter=sql_query_filter,
    )
    if df.empty:
        raise ValueError(f"The table '{table_name}' is empty. No data to ingest.")

    if id_column_name not in df.columns:
        raise ValueError(f"ID column '{id_column_name}' not found in the columns: {df.columns.tolist()}")
    if not set(text_column_names).issubset(df.columns):
        raise ValueError(f"Text columns {text_column_names} not found in the columns: {df.columns.tolist()}")
    if metadata_column_names is not None and not set(metadata_column_names).issubset(df.columns):
        raise ValueError(f"Metadata columns {metadata_column_names} not found in the columns: {df.columns.tolist()}")
    if timestamp_column_name and timestamp_column_name not in df.columns:
        raise ValueError(f"Timestamp column '{timestamp_column_name}' not found in the columns: {df.columns.tolist()}")

    df["text"] = df[text_column_names].apply(lambda x: " ".join(x.astype(str)), axis=1)
    LOGGER.info(f"Retrieved {len(df)} rows from the source table '{table_name}'.")

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    df["chunks"] = df["text"].apply(lambda x: splitter.split_text(x))
    df_chunks = df.explode("chunks", ignore_index=True).rename(columns={"chunks": CHUNK_COLUMN_NAME})
    df_chunks["chunk_index"] = df_chunks.groupby(id_column_name).cumcount() + 1
    df_chunks[ORDER_COLUMN_NAME] = df_chunks["chunk_index"] - 1
    df_chunks[CHUNK_ID_COLUMN_NAME] = df_chunks.apply(lambda _: str(uuid.uuid4()), axis=1)
    df_chunks[FILE_ID_COLUMN_NAME] = table_name + "_" + df_chunks[id_column_name].astype(str)

    columns = [CHUNK_ID_COLUMN_NAME, CHUNK_COLUMN_NAME, FILE_ID_COLUMN_NAME, ORDER_COLUMN_NAME]
    LOGGER.debug(f"Columns to keep: {columns}")
    if timestamp_column_name:
        columns.append(timestamp_column_name)
    if metadata_column_names:
        metadata_column_names = [col for col in metadata_column_names if col not in columns]
        if metadata_column_names:
            LOGGER.debug(f"Metadata columns to keep: {metadata_column_names}")
            columns.extend(metadata_column_names)
    if url_pattern:
        columns.append(URL_COLUMN_NAME)
        df_chunks[URL_COLUMN_NAME] = df_chunks.apply(
            lambda row: url_pattern.format_map({k: ("" if pd.isna(v) else v) for k, v in row.items()}), axis=1
        )

    return df_chunks[columns].copy()


async def upload_db_source(
    db_service: DBService,
    qdrant_service: QdrantService,
    db_definition: DBDefinition,
    storage_schema_name: str,
    storage_table_name: str,
    qdrant_collection_name: str,
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
    # Resolve CURRENT_TIMESTAMP once and use for both SQL and Qdrant
    resolved_timestamp_filter = resolve_sql_timestamp_filter(timestamp_filter)

    if timestamp_filter and resolved_timestamp_filter:
        LOGGER.info(f"Resolved timestamp filter from '{timestamp_filter}' to '{resolved_timestamp_filter}'")

    combined_filter_sql = build_combined_sql_filter(
        query_filter=query_filter,
        timestamp_filter=resolved_timestamp_filter,
        timestamp_column_name=timestamp_column_name,
    )
    combined_filter_qdrant = qdrant_service._build_combined_filter(
        query_filter=query_filter,
        timestamp_filter=resolved_timestamp_filter,
        timestamp_column_name=timestamp_column_name,
    )

    df = get_db_source(
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
    )

    db_service.update_table(
        new_df=df,
        table_name=storage_table_name,
        table_definition=db_definition,
        id_column_name=CHUNK_ID_COLUMN_NAME,
        timestamp_column_name=timestamp_column_name,
        append_mode=update_existing,
        schema_name=storage_schema_name,
        sql_query_filter=combined_filter_sql,
    )
    LOGGER.info(f"Updated table '{storage_table_name}' in schema '{storage_schema_name}' with {len(df)} rows.")
    await sync_chunks_to_qdrant(
        storage_schema_name,
        storage_table_name,
        collection_name=qdrant_collection_name,
        db_service=db_service,
        qdrant_service=qdrant_service,
        sql_query_filter=combined_filter_sql,
        query_filter_qdrant=combined_filter_qdrant,
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

    db_definition, source_type_map = get_db_source_definition(
        timestamp_column_name=timestamp_column_name,
        url_pattern=url_pattern,
        metadata_column_names=metadata_column_names,
        source_db_url=source_db_url,
        source_table_name=source_table_name,
        source_schema_name=source_schema_name,
    )
    metadata_field_types = None
    if metadata_column_names and source_type_map:
        metadata_field_types = {
            field: source_type_map.get(field.lower(), "VARCHAR") for field in metadata_column_names
        }
    qdrant_schema = QdrantCollectionSchema(
        chunk_id_field=CHUNK_ID_COLUMN_NAME,
        content_field=CHUNK_COLUMN_NAME,
        file_id_field=FILE_ID_COLUMN_NAME,
        url_id_field=URL_COLUMN_NAME if url_pattern else None,
        last_edited_ts_field=timestamp_column_name,
        metadata_fields_to_keep=(set(metadata_column_names) if metadata_column_names else None),
        metadata_field_types=metadata_field_types,
    )
    source_type = db.SourceType.DATABASE
    LOGGER.info("Start ingestion data from the database source...")
    await upload_source(
        source_name,
        organization_id,
        task_id,
        source_type,
        qdrant_schema,
        update_existing=update_existing,
        ingestion_function=partial(
            upload_db_source,
            db_definition=db_definition,
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
