from functools import partial
import logging
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
from ingestion_script.utils import upload_source, build_combined_sql_filter

LOGGER = logging.getLogger(__name__)


def get_db_source_definition(
    chunk_id_column_name: str,
    chunk_column_name: str,
    file_id_column_name: str,
    timestamp_column_name: Optional[str] = None,
    url_column_name: Optional[str] = None,
    url_pattern: Optional[str] = None,
    metadata_column_names: Optional[list] = None,
) -> DBDefinition:
    columns = [
        DBColumn(name=PROCESSED_DATETIME_FIELD, type="DATETIME", default="CURRENT_TIMESTAMP"),
        DBColumn(name=chunk_id_column_name, type="VARCHAR", is_primary_key=True),
        DBColumn(name=file_id_column_name, type="VARCHAR"),
        DBColumn(name=chunk_column_name, type="VARCHAR"),
    ]
    if timestamp_column_name:
        columns.append(DBColumn(name=timestamp_column_name, type="VARCHAR"))

    if metadata_column_names:
        existing_names = {c.name for c in columns}
        columns.extend(
            DBColumn(name=col, type="VARCHAR") for col in metadata_column_names if col not in existing_names
        )
    if url_pattern:
        columns.append(DBColumn(name=url_column_name, type="VARCHAR"))

    return DBDefinition(
        columns=columns,
    )


def get_db_source(
    db_url: str,
    table_name: str,
    id_column_name: str,
    text_column_names: list[str],
    chunk_id_column_name: str,
    chunk_column_name: str,
    file_id_column_name: str,
    source_schema_name: Optional[str] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
    url_column_name: Optional[str] = None,
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
    df_chunks = df.explode("chunks", ignore_index=True).rename(columns={"chunks": chunk_column_name})
    df_chunks["chunk_index"] = df_chunks.groupby(id_column_name).cumcount() + 1
    df_chunks[chunk_id_column_name] = (
        df_chunks[id_column_name].astype(str) + "_" + df_chunks["chunk_index"].astype(str)
    )
    df_chunks[file_id_column_name] = table_name + "_" + df_chunks[id_column_name].astype(str)

    columns = [chunk_id_column_name, chunk_column_name, file_id_column_name]
    LOGGER.debug(f"Columns to keep: {columns}")
    if timestamp_column_name:
        columns.append(timestamp_column_name)
    if metadata_column_names:
        metadata_column_names = [col for col in metadata_column_names if col not in columns]
        if metadata_column_names:
            LOGGER.debug(f"Metadata columns to keep: {metadata_column_names}")
            columns.extend(metadata_column_names)
    if url_pattern:
        columns.append(url_column_name)
        df_chunks[url_column_name] = df_chunks.apply(
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
    chunk_id_column_name: str,
    chunk_column_name: str,
    file_id_column_name: str,
    source_schema_name: Optional[str] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
    url_column_name: Optional[str] = None,
    url_pattern: Optional[str] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
    update_existing: bool = False,
    query_filter: Optional[str] = None,
    timestamp_filter: Optional[str] = None,
):
    combined_filter_sql = build_combined_sql_filter(
        query_filter=query_filter,
        timestamp_filter=timestamp_filter,
        timestamp_column_name=timestamp_column_name,
    )
    combined_filter_qdrant = qdrant_service._build_combined_filter(
        query_filter=query_filter,
        timestamp_filter=timestamp_filter,
        timestamp_column_name=timestamp_column_name,
    )

    df = get_db_source(
        db_url=source_db_url,
        table_name=source_table_name,
        id_column_name=id_column_name,
        text_column_names=text_column_names,
        chunk_id_column_name=chunk_id_column_name,
        chunk_column_name=chunk_column_name,
        file_id_column_name=file_id_column_name,
        source_schema_name=source_schema_name,
        metadata_column_names=metadata_column_names,
        timestamp_column_name=timestamp_column_name,
        url_column_name=url_column_name,
        url_pattern=url_pattern,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        sql_query_filter=combined_filter_sql,
    )

    db_service.update_table(
        new_df=df,
        table_name=storage_table_name,
        table_definition=db_definition,
        id_column_name=chunk_id_column_name,
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
    attributes: Optional[dict] = None,
    secret_key: Optional[str] = None,
) -> None:
    chunk_id_column_name = "chunk_id"
    chunk_column_name = "content"
    file_id_column_name = "source_identifier"
    url_column_name = "url"
    qdrant_schema = QdrantCollectionSchema(
        chunk_id_field=chunk_id_column_name,
        content_field=chunk_column_name,
        file_id_field=file_id_column_name,
        url_id_field=url_column_name if url_pattern else None,
        last_edited_ts_field=timestamp_column_name,
        metadata_fields_to_keep=(set(metadata_column_names) if metadata_column_names else None),
    )
    db_definition = get_db_source_definition(
        chunk_id_column_name=chunk_id_column_name,
        chunk_column_name=chunk_column_name,
        file_id_column_name=file_id_column_name,
        timestamp_column_name=timestamp_column_name,
        url_column_name=url_column_name,
        url_pattern=url_pattern,
        metadata_column_names=metadata_column_names,
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
            chunk_id_column_name=chunk_id_column_name,
            chunk_column_name=chunk_column_name,
            file_id_column_name=file_id_column_name,
            metadata_column_names=metadata_column_names,
            timestamp_column_name=timestamp_column_name,
            url_column_name=url_column_name,
            url_pattern=url_pattern,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            query_filter=query_filter,
            timestamp_filter=timestamp_filter,
        ),
        attributes=attributes,
        secret_key=secret_key,
        secret=source_db_url,
    )
