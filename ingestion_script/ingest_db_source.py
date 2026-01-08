import json
import logging
from datetime import datetime
from functools import partial
from typing import Optional
from uuid import UUID

import pandas as pd
from llama_index.core.node_parser import SentenceSplitter

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import SourceAttributes
from engine.qdrant_service import QdrantService
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
    df_chunks[CHUNK_ID_COLUMN_NAME] = (
        df_chunks[id_column_name].astype(str) + "_" + df_chunks["chunk_index"].astype(str)
    )
    df_chunks[FILE_ID_COLUMN_NAME] = table_name + "_" + df_chunks[id_column_name].astype(str)

    if url_pattern:
        df_chunks[URL_COLUMN_NAME] = df_chunks.apply(
            lambda row: url_pattern.format_map({k: ("" if pd.isna(v) else v) for k, v in row.items()}), axis=1
        )
    else:
        df_chunks[URL_COLUMN_NAME] = None

    unified_df = pd.DataFrame()
    unified_df[CHUNK_ID_COLUMN_NAME] = df_chunks[CHUNK_ID_COLUMN_NAME]
    unified_df[CHUNK_COLUMN_NAME] = df_chunks[CHUNK_COLUMN_NAME]
    unified_df[FILE_ID_COLUMN_NAME] = df_chunks[FILE_ID_COLUMN_NAME]
    unified_df[ORDER_COLUMN_NAME] = df_chunks[ORDER_COLUMN_NAME]
    # Use file_id as document_title for database sources (file_id = table_name + "_" + id_column_value)
    unified_df[DOCUMENT_TITLE_COLUMN_NAME] = df_chunks[FILE_ID_COLUMN_NAME]

    if timestamp_column_name and timestamp_column_name in df_chunks.columns:
        unified_df[TIMESTAMP_COLUMN_NAME] = df_chunks[timestamp_column_name]
    else:
        unified_df[TIMESTAMP_COLUMN_NAME] = None

    if URL_COLUMN_NAME in df_chunks.columns:
        unified_df[URL_COLUMN_NAME] = df_chunks[URL_COLUMN_NAME]
    else:
        unified_df[URL_COLUMN_NAME] = None

    def build_metadata(row):
        def serialize_value(value):
            """Convert Timestamp/datetime objects to ISO format strings for JSON serialization."""
            if pd.isna(value):
                return None
            if isinstance(value, pd.Timestamp):
                return value.isoformat()
            if isinstance(value, datetime):
                return value.isoformat()
            return value

        metadata = {}
        if timestamp_column_name and timestamp_column_name in df_chunks.columns:
            timestamp_value = row.get(timestamp_column_name)
            if not pd.isna(timestamp_value):
                metadata[timestamp_column_name] = serialize_value(timestamp_value)
        if metadata_column_names:
            for col in metadata_column_names:
                if col != timestamp_column_name and col in df_chunks.columns:
                    col_value = row.get(col)
                    if not pd.isna(col_value):
                        metadata[col] = serialize_value(col_value)
        return json.dumps(metadata) if metadata else json.dumps({})

    unified_df[METADATA_COLUMN_NAME] = df_chunks.apply(build_metadata, axis=1)

    return unified_df


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

    df[SOURCE_ID_COLUMN_NAME] = str(source_id)

    db_service.update_table(
        new_df=df,
        table_name=storage_table_name,
        table_definition=db_definition,
        id_column_name=CHUNK_ID_COLUMN_NAME,
        timestamp_column_name=TIMESTAMP_COLUMN_NAME,
        append_mode=update_existing,
        schema_name=storage_schema_name,
        sql_query_filter=combined_filter_sql_unified,  # Use unified filter for unified table
        source_id=str(source_id),  # Pass source_id to filter existing IDs by source
    )

    LOGGER.info(f"Updated table '{storage_table_name}' in schema '{storage_schema_name}' with {len(df)} rows.")
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
