from functools import partial
import logging
from typing import Optional

import pandas as pd
from sqlalchemy import UUID

from engine.llm_services.openai_llm_service import OpenAILLMService
from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.storage_service.db_service import DBService
from engine.storage_service.db_utils import (
    PROCESSED_DATETIME_FIELD,
    DBColumn,
    DBDefinition,
    convert_to_correct_pandas_type,
)
from engine.storage_service.local_service import SQLLocalService
from engine.trace.trace_manager import TraceManager
from ingestion_script.ingest_folder_source import sync_chunks_to_qdrant
from ada_backend.database import models as db
from ingestion_script.utils import upload_source

LOGGER = logging.getLogger(__name__)

LLM_OPENAI = OpenAILLMService(trace_manager=TraceManager(project_name="ingestion"))


def get_db_source_definition(
    id_column_name: str, timestamp_column_name: Optional[str] = None, metadata_column_names: Optional[list] = None
) -> DBDefinition:
    columns = [
        DBColumn(name=PROCESSED_DATETIME_FIELD, type="DATETIME", default="CURRENT_TIMESTAMP"),
        DBColumn(name=id_column_name, type="VARCHAR", is_primary_key=True),
        DBColumn(name="table_name", type="VARCHAR"),
        DBColumn(name="content", type="VARCHAR"),
    ]
    if timestamp_column_name:
        columns.append(DBColumn(name=timestamp_column_name, type="VARCHAR"))

    if metadata_column_names:
        columns.extend(DBColumn(name=col, type="VARCHAR") for col in metadata_column_names)
    return DBDefinition(
        columns=columns,
    )


def get_db_source(
    db_url: str,
    table_name: str,
    db_definition: DBDefinition,
    id_column_name: str,
    text_column_names: list[str],
    source_schema_name: Optional[str] = None,
    metadata_column_names: Optional[list[str]] = None,
    timestamp_column_name: Optional[str] = None,
) -> pd.DataFrame:
    sql_local_service = SQLLocalService(engine_url=db_url)
    df = sql_local_service.get_table_df(table_name=table_name, schema_name=source_schema_name)
    if df.empty:
        raise ValueError(f"The table '{table_name}' is empty. No data to ingest.")

    if id_column_name not in df.columns:
        raise ValueError(f"ID column '{id_column_name}' not found in the columns: {df.columns.tolist()}")
    if not set(text_column_names).issubset(df.columns):
        raise ValueError(f"Text columns {text_column_names} not found in the columns: {df.columns.tolist()}")
    if metadata_column_names is not None and not set(metadata_column_names).issubset(df.columns):
        raise ValueError(f"Metadata columns {metadata_column_names} not found in the columns: {df.columns.tolist()}")

    df["content"] = df[text_column_names].apply(lambda x: " ".join(x.astype(str)), axis=1)
    df["table_name"] = table_name
    columns = [id_column_name, "content", "table_name"]
    LOGGER.debug(f"Columns to keep: {columns}")
    if timestamp_column_name:
        columns.append(timestamp_column_name)
    if metadata_column_names:
        columns += metadata_column_names

    df = convert_to_correct_pandas_type(df, id_column_name, db_definition)

    return df[columns].copy()


def upload_db_source(
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
    is_sync_enabled: bool = False,
):
    df = get_db_source(
        db_url=source_db_url,
        table_name=source_table_name,
        db_definition=db_definition,
        id_column_name=id_column_name,
        text_column_names=text_column_names,
        source_schema_name=source_schema_name,
        metadata_column_names=metadata_column_names,
        timestamp_column_name=timestamp_column_name,
    )
    LOGGER.info(f"Retrieved {len(df)} rows from the source table '{source_table_name}'.")
    db_service.update_table(
        new_df=df,
        table_name=storage_table_name,
        table_definition=db_definition,
        id_column_name=id_column_name,
        timestamp_column_name=timestamp_column_name,
        append_mode=not is_sync_enabled,
        schema_name=storage_schema_name,
    )
    LOGGER.info(f"Updated table '{storage_table_name}' in schema '{storage_schema_name}' with {len(df)} rows.")
    sync_chunks_to_qdrant(
        storage_schema_name,
        storage_table_name,
        collection_name=qdrant_collection_name,
        db_service=db_service,
        qdrant_service=qdrant_service,
    )


def ingestion_database(
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
    is_sync_enabled: bool = False,
) -> None:
    qdrant_schema = QdrantCollectionSchema(
        chunk_id_field=id_column_name,
        content_field="content",
        file_id_field="table_name",
        last_edited_ts_field=timestamp_column_name,
        metadata_fields_to_keep=set(metadata_column_names) if metadata_column_names else None,
    )
    db_definition = get_db_source_definition(
        id_column_name=id_column_name,
        timestamp_column_name=timestamp_column_name,
        metadata_column_names=metadata_column_names,
    )
    source_type = db.SourceType.DATABASE
    LOGGER.info("Start ingestion data from the database source...")
    upload_source(
        source_name,
        organization_id,
        task_id,
        source_type,
        qdrant_schema,
        is_sync_enabled=is_sync_enabled,
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
        ),
    )
