import inspect
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import pandas as pd
import requests

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import (
    IngestionTaskUpdate,
    ResultType,
    SourceAttributes,
    TaskResultMetadata,
)
from ada_backend.schemas.source_schema import DataSourceSchema
from data_ingestion.utils import sanitize_filename
from engine.llm_services.llm_service import EmbeddingService, VisionService
from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.storage_service.db_utils import (
    CREATED_AT_COLUMN,
    PROCESSED_DATETIME_FIELD,
    UPDATED_AT_COLUMN,
    DBColumn,
    DBDefinition,
)
from engine.storage_service.local_service import SQLLocalService
from engine.trace.trace_manager import TraceManager
from settings import settings

LOGGER = logging.getLogger(__name__)

TIMESTAMP_COLUMN_NAME = "last_edited_ts"

# Default column names used across database ingestion
CHUNK_ID_COLUMN_NAME = "chunk_id"
CHUNK_COLUMN_NAME = "content"
# TODO: Change file_id to document_id
FILE_ID_COLUMN_NAME = "file_id"
DOCUMENT_TITLE_COLUMN_NAME = "document_title"
ORDER_COLUMN_NAME = "order"
URL_COLUMN_NAME = "url"
SOURCE_ID_COLUMN_NAME = "source_id"
METADATA_COLUMN_NAME = "metadata"  # JSONB column for source-specific metadata

DEFAULT_EMBEDDING_MODEL = "openai:text-embedding-3-large"

# Columns required for the unified database table
UNIFIED_TABLE_COLUMNS = [
    CHUNK_ID_COLUMN_NAME,
    SOURCE_ID_COLUMN_NAME,
    ORDER_COLUMN_NAME,
    FILE_ID_COLUMN_NAME,
    DOCUMENT_TITLE_COLUMN_NAME,
    URL_COLUMN_NAME,
    CHUNK_COLUMN_NAME,
    TIMESTAMP_COLUMN_NAME,
    METADATA_COLUMN_NAME,
]

# Unified table definition for all source types
UNIFIED_TABLE_DEFINITION = DBDefinition(
    columns=[
        DBColumn(name=PROCESSED_DATETIME_FIELD, type="DATETIME", default="CURRENT_TIMESTAMP"),
        DBColumn(name=CHUNK_ID_COLUMN_NAME, type="VARCHAR", is_primary=True),
        DBColumn(name=SOURCE_ID_COLUMN_NAME, type="UUID", is_primary=True),
        DBColumn(name=ORDER_COLUMN_NAME, type="INTEGER", is_nullable=True),
        DBColumn(name=FILE_ID_COLUMN_NAME, type="VARCHAR"),
        DBColumn(name=DOCUMENT_TITLE_COLUMN_NAME, type="VARCHAR"),
        DBColumn(name=URL_COLUMN_NAME, type="VARCHAR", is_nullable=True),
        DBColumn(name=CHUNK_COLUMN_NAME, type="VARCHAR"),
        DBColumn(name=TIMESTAMP_COLUMN_NAME, type="VARCHAR"),
        DBColumn(name=METADATA_COLUMN_NAME, type="JSONB"),
        DBColumn(name=CREATED_AT_COLUMN, type="TIMESTAMP_TZ", default="CURRENT_TIMESTAMP"),
        DBColumn(name=UPDATED_AT_COLUMN, type="TIMESTAMP_TZ", default="CURRENT_TIMESTAMP"),
    ]
)

# Unified Qdrant schema for all source types
# Note: metadata_fields_to_keep is None because we flatten metadata into separate columns
UNIFIED_QDRANT_SCHEMA = QdrantCollectionSchema(
    chunk_id_field=CHUNK_ID_COLUMN_NAME,
    content_field=CHUNK_COLUMN_NAME,
    url_id_field=URL_COLUMN_NAME,
    file_id_field=FILE_ID_COLUMN_NAME,
    last_edited_ts_field=TIMESTAMP_COLUMN_NAME,
    metadata_fields_to_keep=None,
    source_id_field=SOURCE_ID_COLUMN_NAME,
)


def _build_flattened_metadata(row) -> str:
    """Build flattened metadata by merging metadata dict into top level."""
    metadata_dict = {
        "document_title": row.get("document_title"),
        "url": row.get("url"),
    }

    # Flatten the nested metadata dict
    metadata_value = row.get("metadata", {})
    if isinstance(metadata_value, str):
        try:
            metadata_value = json.loads(metadata_value)
        except (json.JSONDecodeError, TypeError):
            metadata_value = {}

    if isinstance(metadata_value, dict):
        metadata_dict.update(metadata_value)

    return json.dumps(metadata_dict, ensure_ascii=False)


def transform_chunks_df_for_unified_table(
    chunks_df: pd.DataFrame,
    source_id: UUID,
) -> pd.DataFrame:
    """
    Transform a raw chunks DataFrame into the unified table schema format.

    This function:
    1. Builds flattened metadata from document_title, url, and existing metadata
    2. Renames columns to match unified table schema
    3. Adds source_id column
    4. Returns only the required columns for the database

    Args:
        chunks_df: Raw DataFrame from document chunking (with columns like file_id,
                   chunk_id, content, document_title, url, metadata, etc.)
        source_id: UUID of the source to associate with all chunks

    Returns:
        DataFrame with only the unified table columns ready for database insertion
    """
    df = chunks_df.copy()

    # Build flattened metadata JSON from document_title, url, and existing metadata
    df[METADATA_COLUMN_NAME] = df.apply(_build_flattened_metadata, axis=1)

    # Rename columns to match unified table schema
    df = df.rename(
        columns={
            "chunk_id": CHUNK_ID_COLUMN_NAME,
            "file_id": FILE_ID_COLUMN_NAME,
            "document_title": DOCUMENT_TITLE_COLUMN_NAME,
            "url": URL_COLUMN_NAME,
            "content": CHUNK_COLUMN_NAME,
            "last_edited_ts": TIMESTAMP_COLUMN_NAME,
        }
    )

    # Add source_id column
    df[SOURCE_ID_COLUMN_NAME] = str(source_id)

    # Select only the required columns for the database
    return df[UNIFIED_TABLE_COLUMNS]


def get_sanitize_names(
    organization_id: str,
    embedding_model_reference: Optional[str] = DEFAULT_EMBEDDING_MODEL,
) -> tuple[str, str, str]:
    """
    Generate sanitized schema, table, and collection names.

    All sources use org-level table and collection in the public schema.
    Collection name includes embedding model to avoid mixing vectors from different models.
    """
    sanitize_organization_id = sanitize_filename(organization_id)
    schema_name = "public"
    table_name = f"org_{sanitize_organization_id}_chunks"

    sanitized_model = sanitize_filename(embedding_model_reference.replace(":", "_").replace("-", "_"))
    qdrant_collection_name = f"org_{sanitize_organization_id}_{sanitized_model}_collection"

    return (
        schema_name,
        table_name,
        qdrant_collection_name,
    )


def check_signature(fn: callable, required_params: list[str]):
    sig = inspect.signature(fn)
    fn_params = list(sig.parameters.keys())
    missing = [p for p in required_params if p not in fn_params]
    if missing:
        raise ValueError(
            f"Function {fn.__name__} is missing required parameters: {', '.join(missing)}. "
            f"Expected parameters: {', '.join(required_params)}"
        )


def update_ingestion_task(
    organization_id: str,
    ingestion_task: IngestionTaskUpdate,
) -> None:
    """Update the status of an ingestion task in the database."""
    api_url = f"{str(settings.ADA_URL)}/ingestion_task/{organization_id}"
    LOGGER.info(
        f"[API_CALL] Starting update_ingestion_task - URL: {api_url}, "
        f"Task ID: {ingestion_task.id}, Status: {ingestion_task.status}"
    )

    try:
        response = requests.patch(
            api_url,
            json=ingestion_task.model_dump(mode="json"),
            headers={
                "x-ingestion-api-key": settings.INGESTION_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=30,  # Add timeout to prevent hanging
        )
        LOGGER.info(
            f"[API_CALL] update_ingestion_task response - Status: {response.status_code}, Task ID: {ingestion_task.id}"
        )
        response.raise_for_status()
        LOGGER.info(f"[API_CALL] Successfully updated ingestion task - Task ID: {ingestion_task.id}")
    except requests.exceptions.Timeout as e:
        LOGGER.error(
            f"[API_CALL] TIMEOUT updating ingestion task - Task ID: {ingestion_task.id}, "
            f"URL: {api_url}, Error: {str(e)}"
        )
        raise requests.exceptions.RequestException(
            f"Timeout updating ingestion task for organization {organization_id}: {str(e)}"
        ) from e
    except requests.exceptions.ConnectionError as e:
        LOGGER.error(
            f"[API_CALL] CONNECTION ERROR updating ingestion task - Task ID: {ingestion_task.id}, "
            f"URL: {api_url}, Error: {str(e)}"
        )
        raise requests.exceptions.RequestException(
            f"Connection error updating ingestion task for organization {organization_id}: {str(e)}"
        ) from e
    except Exception as e:
        LOGGER.error(
            f"[API_CALL] FAILED updating ingestion task - Task ID: {ingestion_task.id}, "
            f"URL: {api_url}, Error: {str(e)}"
        )
        raise requests.exceptions.RequestException(
            f"Failed to update ingestion task for organization {organization_id}: {str(e)}"
        ) from e


def create_source(
    organization_id: str,
    source_data: DataSourceSchema,
) -> UUID:
    """Create a source in the database."""
    api_url = f"{str(settings.ADA_URL)}/sources/{organization_id}"
    LOGGER.info(
        f"[API_CALL] Starting create_source - URL: {api_url}, "
        f"Source: {source_data.name}, Organization: {organization_id}"
    )

    try:
        response = requests.post(
            api_url,
            json=source_data.model_dump(mode="json"),
            headers={
                "x-ingestion-api-key": settings.INGESTION_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=30,  # Add timeout to prevent hanging
        )
        LOGGER.info(f"[API_CALL] create_source response - Status: {response.status_code}, Source: {source_data.name}")
        response.raise_for_status()
        LOGGER.info(
            f"[API_CALL] Successfully created source - Name: {source_data.name}, Organization: {organization_id}"
        )
        return response.json()
    except requests.exceptions.Timeout as e:
        LOGGER.error(
            f"[API_CALL] TIMEOUT creating source - Source: {source_data.name}, URL: {api_url}, Error: {str(e)}"
        )
        raise requests.exceptions.RequestException(
            f"Timeout creating source for organization {organization_id}: {str(e)}"
        ) from e
    except requests.exceptions.ConnectionError as e:
        LOGGER.error(
            f"[API_CALL] CONNECTION ERROR creating source - Source: {source_data.name}, "
            f"URL: {api_url}, Error: {str(e)}"
        )
        raise requests.exceptions.RequestException(
            f"Connection error creating source for organization {organization_id}: {str(e)}"
        ) from e
    except Exception as e:
        LOGGER.error(
            f"[API_CALL] FAILED creating source - Source: {source_data.name}, URL: {api_url}, Error: {str(e)}"
        )
        raise requests.exceptions.RequestException(
            f"Failed to create source for organization {organization_id}: "
            f"{str(e)} with the data {source_data.model_dump(mode='json')}"
        ) from e


async def upload_source(
    source_name: str,
    organization_id: str,
    task_id: str,
    source_type: db.SourceType,
    qdrant_schema: QdrantCollectionSchema,
    ingestion_function: callable,
    update_existing: bool = False,
    attributes: Optional[SourceAttributes] = None,
    source_id: Optional[UUID] = None,
) -> None:
    check_signature(
        ingestion_function,
        required_params=[
            "db_service",
            "qdrant_service",
            "storage_schema_name",
            "storage_table_name",
            "qdrant_collection_name",
            "source_id",
        ],
    )
    if settings.INGESTION_DB_URL is None:
        raise ValueError("INGESTION_DB_URL is not set")
    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    if source_id:
        result_source_id = source_id
        update_task = True
    else:
        result_source_id = uuid.uuid4()
        update_task = False

    embedding_service = EmbeddingService(
        provider="openai",
        model_name="text-embedding-3-large",
        trace_manager=TraceManager(project_name="ingestion"),
    )
    embedding_model_ref = f"{embedding_service._provider}:{embedding_service._model_name}"
    schema_name, table_name, qdrant_collection_name = get_sanitize_names(
        organization_id=organization_id,
        embedding_model_reference=embedding_model_ref,
    )

    ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.FAILED,
        source_id=result_source_id,
    )
    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
    )

    try:
        await ingestion_function(
            db_service=db_service,
            qdrant_service=qdrant_service,
            storage_schema_name=schema_name,
            storage_table_name=table_name,
            qdrant_collection_name=qdrant_collection_name,
            update_existing=update_existing,
            source_id=result_source_id,
        )
    except Exception as e:
        error_msg = f"Failed to get data from the database: {str(e)}"
        LOGGER.error(error_msg)
        ingestion_task = IngestionTaskUpdate(
            id=task_id,
            source_name=source_name,
            source_type=source_type,
            status=db.TaskStatus.FAILED,
            result_metadata=TaskResultMetadata(
                message=error_msg,
                type=ResultType.ERROR,
            ),
        )
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        return

    source_data = DataSourceSchema(
        id=result_source_id,
        name=source_name,
        type=source_type,
        database_schema=schema_name,
        database_table_name=table_name,
        qdrant_collection_name=qdrant_collection_name,
        qdrant_schema=qdrant_schema.to_dict(),
        embedding_model_reference=embedding_model_ref,
        attributes=attributes,
    )
    if not update_task:
        create_source(
            organization_id=organization_id,
            source_data=source_data,
        )
    LOGGER.info(f"Upserting source {source_name} for organization {organization_id} in database")

    ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_id=result_source_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.COMPLETED,
    )

    LOGGER.info(f" Update status {source_name} source for organization {organization_id} in database")
    update_ingestion_task(
        organization_id=organization_id,
        ingestion_task=ingestion_task,
    )
    LOGGER.info(f"Successfully ingested {source_name} source for organization {organization_id}")


def build_combined_sql_filter(
    query_filter: Optional[str],
    timestamp_filter: Optional[str],
    timestamp_column_name: Optional[str],
) -> Optional[str]:
    """Combine query_filter and timestamp_filter into a single SQL WHERE clause."""
    filters = []
    if query_filter:
        filters.append(f"({query_filter})")
    if timestamp_filter and timestamp_column_name:
        filters.append(f"({timestamp_column_name} IS NOT NULL AND {timestamp_column_name} {timestamp_filter})")
    if filters:
        return " AND ".join(filters)
    return None


def _extract_column_names_from_sql(sql_filter: str) -> set[str]:
    """
    Extract column names from a SQL WHERE clause.

    This function uses regex to identify SQL identifiers that are likely column names.
    It looks for identifiers that appear in contexts where columns are expected.
    It excludes identifiers that appear inside string literals.

    Args:
        sql_filter: SQL WHERE clause

    Returns:
        Set of column names found in the SQL (lowercase)
    """
    # SQL keywords that should not be considered as column names
    sql_keywords = {
        "select",
        "from",
        "where",
        "and",
        "or",
        "not",
        "in",
        "is",
        "null",
        "like",
        "between",
        "exists",
        "case",
        "when",
        "then",
        "else",
        "end",
        "as",
        "on",
        "join",
        "inner",
        "left",
        "right",
        "outer",
        "union",
        "all",
        "distinct",
        "group",
        "by",
        "having",
        "order",
        "asc",
        "desc",
        "limit",
        "offset",
        "count",
        "sum",
        "avg",
        "max",
        "min",
        "cast",
        "coalesce",
        "extract",
        "date",
        "time",
        "timestamp",
        "interval",
        "true",
        "false",
        "current_date",
        "current_time",
        "current_timestamp",
        "now",
        "upper",
        "lower",
        "trim",
        "substring",
        "length",
        "replace",
        "concat",
        "abs",
        "round",
        "floor",
        "ceil",
        "mod",
        "power",
    }

    # Remove string literals to avoid extracting column names from inside them
    # This regex matches single-quoted strings, handling escaped quotes
    sql_without_strings = re.sub(r"'([^'\\]|\\.)*'", "''", sql_filter)

    # Pattern to match SQL identifiers (column names)
    # Matches: word characters, optionally quoted identifiers, or identifiers with dots
    # We look for identifiers that are not SQL keywords
    pattern = r"\b([a-z_][a-z0-9_]*)\b"

    # Find all potential identifiers (from SQL without string literals)
    matches = re.findall(pattern, sql_without_strings.lower())

    # Filter out SQL keywords, but keep words that appear in column contexts
    # (e.g., followed by comparison operators, IS, etc. - these are likely column names)
    column_names = set()
    sql_lower = sql_without_strings.lower()

    for match in matches:
        if match not in sql_keywords:
            column_names.add(match)
        else:
            # Check if keyword appears in a column context (not as a function)
            # Look for patterns like: "date <", "date >", "date =", "date IS", etc.
            # These indicate it's being used as a column name, not a function
            escaped_match = re.escape(match)
            # Pattern: word boundary, keyword, whitespace, then comparison operator or IS
            column_context_pattern = rf"\b{escaped_match}\b\s*(<|>|<=|>=|=|!=|<>|IS|IS NOT)"
            if re.search(column_context_pattern, sql_lower, re.IGNORECASE):
                column_names.add(match)

    return column_names


def map_source_filter_to_unified_table_filter(
    sql_filter: Optional[str],
    timestamp_column_name: Optional[str],
) -> Optional[str]:
    """
    Map a SQL filter from source database columns to unified table columns.
    """
    if not sql_filter:
        return None
    LOGGER.info(f"Mapping source filter to unified table filter: {sql_filter}")
    unified_columns = {col.name.lower() for col in UNIFIED_TABLE_DEFINITION.columns}

    columns_in_filter = _extract_column_names_from_sql(sql_filter)
    LOGGER.info(f"Columns in filter: {columns_in_filter}")

    mapped_filter = sql_filter

    def replace_column_name(text: str, col_name: str, replacement: str) -> str:
        """
        Replace column name in SQL, avoiding matches inside string literals.
        Processes the SQL by splitting on string literals and only replacing in non-string parts.
        """
        escaped_col = re.escape(col_name)
        pattern = rf"\b{escaped_col}\b"

        parts = []
        current_pos = 0
        i = 0
        in_string = False

        while i < len(text):
            char = text[i]
            if char == "'":
                if i > 0 and text[i - 1] == "\\":
                    i += 1
                    continue

                if not in_string:
                    if i > current_pos:
                        part = text[current_pos:i]
                        part = re.sub(pattern, replacement, part, flags=re.IGNORECASE)
                        parts.append(part)
                    parts.append("'")
                    in_string = True
                    current_pos = i + 1
                else:
                    parts.append(text[current_pos : i + 1])
                    in_string = False
                    current_pos = i + 1
            i += 1

        if current_pos < len(text):
            part = text[current_pos:]
            if not in_string:
                part = re.sub(pattern, replacement, part, flags=re.IGNORECASE)
            parts.append(part)

        return "".join(parts)

    for col in columns_in_filter:
        col_lower = col.lower()

        if col_lower not in unified_columns:
            replacement = f"{METADATA_COLUMN_NAME}->>'{col}'"
            mapped_filter = replace_column_name(mapped_filter, col, replacement)
        elif timestamp_column_name and col_lower == timestamp_column_name.lower():
            replacement = TIMESTAMP_COLUMN_NAME
            mapped_filter = replace_column_name(mapped_filter, col, replacement)

    return mapped_filter


def get_first_available_multimodal_custom_llm():
    custom_models = settings.custom_models
    if custom_models is None or custom_models.get("custom_models") is None:
        return None
    for provider, models in custom_models["custom_models"].items():
        for model in models:
            if "image" in model.get("model_capacity", []):
                return VisionService(
                    trace_manager=TraceManager(project_name="ingestion"),
                    provider=provider,
                    model_name=model.get("name"),
                    temperature=0.0,
                )


def get_first_available_embeddings_custom_llm() -> EmbeddingService | None:
    custom_models = settings.custom_models
    if custom_models is None or custom_models.get("custom_models") is None:
        return None
    for provider, models in custom_models["custom_models"].items():
        for model in models:
            if "embedding" in model.get("model_capacity", []):
                return EmbeddingService(
                    provider=provider,
                    model_name=model.get("name"),
                    trace_manager=TraceManager(project_name="ingestion"),
                    embedding_size=model.get("embedding_size"),
                )


def resolve_sql_timestamp_filter(timestamp_filter: Optional[str]) -> Optional[str]:
    if not timestamp_filter:
        return timestamp_filter

    filter_with_resolved_functions = timestamp_filter.strip()
    current_date_string = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for func in [
        "NOW()",
        "now()",
        "CURRENT_TIMESTAMP",
        "current_timestamp",
        "CURRENT_TIMESTAMP()",
        "current_timestamp()",
    ]:
        if func in filter_with_resolved_functions:
            filter_with_resolved_functions = filter_with_resolved_functions.replace(func, f"'{current_date_string}'")
    return filter_with_resolved_functions
