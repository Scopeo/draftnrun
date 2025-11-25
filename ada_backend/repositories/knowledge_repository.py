import json
import logging
from contextlib import contextmanager
from typing import Any, Dict, List

from sqlalchemy import func, select, update, delete

from ada_backend.schemas.knowledge_schema import KnowledgeChunk
from ada_backend.services.knowledge.errors import (
    KnowledgeServiceChunkNotFoundError,
    KnowledgeServiceChunkAlreadyExistsError,
    KnowledgeServiceFileNotFoundError,
)
from engine.storage_service.local_service import SQLLocalService
from engine.storage_service.db_utils import PROCESSED_DATETIME_FIELD, get_default_value_for_column_type


LOGGER = logging.getLogger(__name__)


def _deserialize_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _get_table(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
):
    return sql_local_service.get_table(table_name=table_name, schema_name=schema_name)


def _prepare_chunk_data_for_table(
    chunk: KnowledgeChunk,
    table_description: List[Dict[str, Any]],
    include_defaults: bool = True,
) -> Dict[str, Any]:
    """Prepare chunk data matching table columns, optionally with default values for missing fields.

    Args:
        chunk: KnowledgeChunk object
        table_description: Table description from describe_table()
        include_defaults: If True, add default values for missing columns (for CREATE).
                         If False, only include fields present in chunk (for UPDATE).

    Returns:
        Dictionary with chunk fields matched to table columns, including defaults if specified
    """
    table_column_names = {col["name"] for col in table_description}
    chunk_dict = chunk.model_dump(exclude_none=True)

    data = {}

    for field_name, field_value in chunk_dict.items():
        if field_name in table_column_names:
            data[field_name] = field_value

    if include_defaults:
        for column in table_description:
            column_name = column["name"]
            if column_name == PROCESSED_DATETIME_FIELD or column_name == "_processed_datetime":
                continue
            if column_name not in data:
                column_type = column.get("type", "")
                if column_type:
                    try:
                        default_value = get_default_value_for_column_type(column_type)
                        data[column_name] = default_value
                    except ValueError:
                        LOGGER.warning(
                            f"Unknown column type '{column_type}' for column '{column_name}', skipping default value"
                        )
                        data[column_name] = ""
                else:
                    data[column_name] = ""
    return data


@contextmanager
def _execute_statement(
    sql_local_service: SQLLocalService,
    stmt,
):
    """Execute a SQL statement within a session context with error handling.

    Yields:
        tuple: (result, session) - The result object and session.
        The caller can use result methods (.all(), .fetchone(), .scalar(), etc.)
        and call session.commit() if needed for writes.
    """
    try:
        with sql_local_service.Session() as session:
            result = session.execute(stmt)
            yield result, session
    except Exception as e:
        LOGGER.error(f"Error executing statement: {str(e)}", exc_info=True)
        raise


def list_files_for_source(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
) -> List[Dict[str, Any]]:
    table = _get_table(sql_local_service, schema_name, table_name)
    stmt = (
        select(
            table.c.file_id.label("file_id"),
            func.max(table.c.document_title).label("document_title"),
            func.count().label("chunk_count"),
            func.max(table.c.last_edited_ts).label("last_edited_ts"),
        )
        .group_by(table.c.file_id)
        .order_by(func.max(table.c.last_edited_ts).desc())
    )
    with _execute_statement(sql_local_service, stmt) as (result, session):
        rows = result.all()

    files: List[Dict[str, Any]] = []
    for row in rows:
        files.append(
            {
                "file_id": row.file_id,
                "document_title": row.document_title,
                "chunk_count": int(row.chunk_count),
                "last_edited_ts": row.last_edited_ts,
            }
        )
    return files


def get_file_with_chunks(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    file_id: str,
) -> Dict[str, Any]:
    rows, table = get_chunk_rows_for_file(sql_local_service, schema_name, table_name, file_id)

    if not rows:
        raise KnowledgeServiceFileNotFoundError(f"No chunks found for file_id='{file_id}' in table '{table_name}'")

    chunks: List[Dict[str, Any]] = []
    for row in rows:
        row_dict = {column.name: getattr(row, column.name) for column in table.columns}
        row_dict["metadata"] = _deserialize_json_field(row_dict.get("metadata"))
        row_dict["bounding_boxes"] = _deserialize_json_field(row_dict.get("bounding_boxes"))
        if row_dict["metadata"] is None:
            row_dict["metadata"] = {}
        chunks.append(row_dict)

    first_chunk = chunks[0]
    file_metadata = {
        "file_id": first_chunk.get("file_id"),
        "document_title": first_chunk.get("document_title"),
        "url": first_chunk.get("url"),
        "metadata": first_chunk.get("metadata") or {},
        "last_edited_ts": first_chunk.get("last_edited_ts"),
        "folder_name": None,
    }

    metadata = first_chunk.get("metadata")
    if isinstance(metadata, dict) and "folder_name" in metadata:
        file_metadata["folder_name"] = metadata.get("folder_name")

    return {
        "file": file_metadata,
        "chunks": chunks,
    }


def get_chunk_by_id(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    chunk_id: str,
) -> Dict[str, Any]:
    table = _get_table(sql_local_service, schema_name, table_name)
    stmt = select(table).where(table.c.chunk_id == chunk_id)
    with _execute_statement(sql_local_service, stmt) as (result, session):
        row = result.fetchone()

    if row is None:
        raise KnowledgeServiceChunkNotFoundError(f"Chunk with id='{chunk_id}' not found in table '{table_name}'")

    row_dict = {column.name: getattr(row, column.name) for column in table.columns}
    row_dict["metadata"] = _deserialize_json_field(row_dict.get("metadata"))
    row_dict["bounding_boxes"] = _deserialize_json_field(row_dict.get("bounding_boxes"))
    if row_dict["metadata"] is None:
        row_dict["metadata"] = {}
    return row_dict


def get_chunk_rows_for_file(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    file_id: str,
) -> tuple:
    """Get all chunk rows for a given file_id, sorted by chunk_id. Returns (rows, table)."""
    table = _get_table(sql_local_service, schema_name, table_name)
    stmt = select(table).where(table.c.file_id == file_id).order_by(table.c.chunk_id)
    with _execute_statement(sql_local_service, stmt) as (result, session):
        rows = result.fetchall()
    return rows, table


def get_chunk_ids_for_file(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    file_id: str,
) -> List[str]:
    """Get all chunk_ids for a given file_id, sorted by chunk_id."""
    rows, table = get_chunk_rows_for_file(sql_local_service, schema_name, table_name, file_id)
    return [getattr(row, "chunk_id") for row in rows]


def file_exists(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    file_id: str,
) -> bool:
    table = _get_table(sql_local_service, schema_name, table_name)
    stmt = select(func.count()).select_from(table).where(table.c.file_id == file_id)
    with _execute_statement(sql_local_service, stmt) as (result, session):
        count = result.scalar()

    return bool(count)


def delete_file(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    file_id: str,
) -> None:
    table = _get_table(sql_local_service, schema_name, table_name)
    stmt = delete(table).where(table.c.file_id == file_id)
    with _execute_statement(sql_local_service, stmt) as (result, session):
        if result.rowcount == 0:
            raise KnowledgeServiceFileNotFoundError(f"No rows deleted for file_id='{file_id}' in table '{table_name}'")
        session.commit()


def create_chunk(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    chunk: KnowledgeChunk,
) -> KnowledgeChunk:
    """
    Create a chunk in the database.

    Args:
        sql_local_service: SQL service instance
        schema_name: Schema name
        table_name: Table name
        chunk: KnowledgeChunk object with all required fields

    Returns:
        KnowledgeChunk object
    """
    table = _get_table(sql_local_service, schema_name, table_name)
    table_description = sql_local_service.describe_table(table_name=table_name, schema_name=schema_name)
    payload = _prepare_chunk_data_for_table(chunk, table_description)

    chunk_id = chunk.chunk_id

    exists_stmt = select(table.c.chunk_id).where(table.c.chunk_id == chunk_id)
    with _execute_statement(sql_local_service, exists_stmt) as (result, session):
        existing = result.scalar_one_or_none()
        if existing:
            raise KnowledgeServiceChunkAlreadyExistsError(
                f"Chunk with id='{chunk_id}' already exists in table '{table_name}'"
            )

    sql_local_service.insert_data(table_name=table_name, data=payload, schema_name=schema_name)

    return chunk


def update_chunk(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    chunk: KnowledgeChunk,
) -> KnowledgeChunk:
    """
    Update a chunk in the database.

    Args:
        sql_local_service: SQL service instance
        schema_name: Schema name
        table_name: Table name
        chunk: KnowledgeChunk object with updated fields

    Returns:
        KnowledgeChunk object
    """
    table = _get_table(sql_local_service, schema_name, table_name)
    table_description = sql_local_service.describe_table(table_name=table_name, schema_name=schema_name)
    # For UPDATE, only include fields present in chunk, don't add defaults (preserve existing values)
    update_values = _prepare_chunk_data_for_table(chunk, table_description, include_defaults=False)
    update_values = SQLLocalService.add_processed_datetime_if_exists(table, update_values)
    stmt = update(table).where(table.c.chunk_id == chunk.chunk_id).values(**update_values)
    with _execute_statement(sql_local_service, stmt) as (result, session):
        if result.rowcount == 0:
            raise KnowledgeServiceChunkNotFoundError(
                f"Chunk with id='{chunk.chunk_id}' not found in table '{table_name}'"
            )
        session.commit()

    return chunk


def delete_chunk(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    chunk_id: str,
) -> None:
    table = _get_table(sql_local_service, schema_name, table_name)
    stmt = delete(table).where(table.c.chunk_id == chunk_id)
    with _execute_statement(sql_local_service, stmt) as (result, session):
        if result.rowcount == 0:
            raise KnowledgeServiceChunkNotFoundError(f"Chunk with id='{chunk_id}' not found in table '{table_name}'")
        session.commit()
