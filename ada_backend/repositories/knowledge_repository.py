import json
import logging
from typing import Any, Dict, List

from sqlalchemy import func, select, update, delete

from ada_backend.schemas.knowledge_schema import KnowledgeChunk
from engine.storage_service.local_service import SQLLocalService


LOGGER = logging.getLogger(__name__)


def _deserialize_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def list_files_for_source(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
) -> List[Dict[str, Any]]:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    with sql_local_service.Session() as session:
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
        rows = session.execute(stmt).all()

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
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)

    with sql_local_service.Session() as session:
        stmt = (
            select(table)
            .where(table.c.file_id == file_id)
            .order_by(table.c.last_edited_ts.desc(), table.c.chunk_id.desc())
        )
        rows = session.execute(stmt).fetchall()

    if not rows:
        raise ValueError(f"No chunks found for file_id='{file_id}' in table '{table_name}'")

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
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)

    with sql_local_service.Session() as session:
        stmt = select(table).where(table.c.chunk_id == chunk_id)
        row = session.execute(stmt).fetchone()

    if row is None:
        raise ValueError(f"Chunk with id='{chunk_id}' not found in table '{table_name}'")

    row_dict = {column.name: getattr(row, column.name) for column in table.columns}
    row_dict["metadata"] = _deserialize_json_field(row_dict.get("metadata"))
    row_dict["bounding_boxes"] = _deserialize_json_field(row_dict.get("bounding_boxes"))
    if row_dict["metadata"] is None:
        row_dict["metadata"] = {}
    return row_dict


def file_exists(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    file_id: str,
) -> bool:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)

    with sql_local_service.Session() as session:
        stmt = select(func.count()).select_from(table).where(table.c.file_id == file_id)
        count = session.execute(stmt).scalar()

    return bool(count)


def delete_file(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    file_id: str,
) -> None:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)

    with sql_local_service.Session() as session:
        stmt = delete(table).where(table.c.file_id == file_id)
        result = session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(f"No rows deleted for file_id='{file_id}' in table '{table_name}'")
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
    from engine.storage_service.db_utils import PROCESSED_DATETIME_FIELD, get_default_value_for_column_type

    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    table_description = sql_local_service.describe_table(table_name=table_name, schema_name=schema_name)
    table_column_names = {col["name"] for col in table_description}

    chunk_id = chunk.chunk_id
    chunk_dict = chunk.model_dump(exclude_none=True)

    # Prepare payload: match chunk fields with table columns
    payload = {}

    # Add matching fields from chunk to table
    for field_name, field_value in chunk_dict.items():
        if field_name in table_column_names:
            payload[field_name] = field_value
        # Exclude fields not in table (no error, just ignore them)

    # Add default values for missing table columns (excluding processed_datetime)
    for column in table_description:
        column_name = column["name"]
        if column_name == PROCESSED_DATETIME_FIELD or column_name == "_processed_datetime":
            continue
        if column_name not in payload:
            column_type = column.get("type", "")
            default_value = get_default_value_for_column_type(column_type)
            payload[column_name] = default_value

    with sql_local_service.Session() as session:
        exists_stmt = select(table.c.chunk_id).where(table.c.chunk_id == chunk_id)
        existing = session.execute(exists_stmt).scalar_one_or_none()
        if existing:
            raise ValueError(f"Chunk with id='{chunk_id}' already exists in table '{table_name}'")

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
    from engine.storage_service.db_utils import PROCESSED_DATETIME_FIELD, get_default_value_for_column_type

    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    table_description = sql_local_service.describe_table(table_name=table_name, schema_name=schema_name)
    table_column_names = {col["name"] for col in table_description}

    chunk_dict = chunk.model_dump(exclude_none=True)

    # Prepare update values: match chunk fields with table columns
    update_values = {}

    # Add matching fields from chunk to table
    for field_name, field_value in chunk_dict.items():
        if field_name in table_column_names:
            update_values[field_name] = field_value
        # Exclude fields not in table (no error, just ignore them)

    # Add default values for missing table columns (excluding processed_datetime)
    for column in table_description:
        column_name = column["name"]
        if column_name == PROCESSED_DATETIME_FIELD or column_name == "_processed_datetime":
            continue
        if column_name not in update_values:
            column_type = column.get("type", "")
            default_value = get_default_value_for_column_type(column_type)
            update_values[column_name] = default_value

    update_values = SQLLocalService.add_processed_datetime_if_exists(table, update_values)

    with sql_local_service.Session() as session:
        stmt = update(table).where(table.c.chunk_id == chunk.chunk_id).values(**update_values)
        result = session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(f"Chunk with id='{chunk.chunk_id}' not found in table '{table_name}'")
        session.commit()

    return chunk


def delete_chunk(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    chunk_id: str,
) -> None:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)

    with sql_local_service.Session() as session:
        stmt = delete(table).where(table.c.chunk_id == chunk_id)
        result = session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(f"Chunk with id='{chunk_id}' not found in table '{table_name}'")
        session.commit()
