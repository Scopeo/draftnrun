import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update, delete

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


def update_file_metadata(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    file_id: str,
    document_title: Optional[str] = None,
    url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)

    update_values: Dict[str, Any] = {}
    if document_title is not None:
        update_values["document_title"] = document_title
    if url is not None:
        update_values["url"] = url
    if metadata is not None:
        update_values["metadata"] = metadata

    if not update_values:
        raise ValueError("No update values provided for file metadata update")

    with sql_local_service.Session() as session:
        stmt = update(table).where(table.c.file_id == file_id).values(**update_values)
        result = session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(f"No rows updated for file_id='{file_id}' in table '{table_name}'")
        session.commit()


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
    chunk_id: str,
    file_id: str,
    content: str,
    document_title: Optional[str],
    url: Optional[str],
    metadata: Optional[Dict[str, Any]],
    bounding_boxes: Optional[List[Dict[str, Any]]],
    last_edited_ts: Optional[str],
) -> Dict[str, Any]:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)

    with sql_local_service.Session() as session:
        exists_stmt = select(table.c.chunk_id).where(table.c.chunk_id == chunk_id)
        existing = session.execute(exists_stmt).scalar_one_or_none()
        if existing:
            raise ValueError(f"Chunk with id='{chunk_id}' already exists in table '{table_name}'")

    payload: Dict[str, Any] = {
        "chunk_id": chunk_id,
        "file_id": file_id,
        "content": content,
        "document_title": document_title,
        "url": url,
        "metadata": metadata or {},
        "bounding_boxes": json.dumps(bounding_boxes) if bounding_boxes else None,
        "last_edited_ts": last_edited_ts or datetime.utcnow().isoformat(),
    }

    sql_local_service.insert_data(table_name=table_name, data=payload, schema_name=schema_name)

    return get_chunk_by_id(sql_local_service, schema_name, table_name, chunk_id)


def update_chunk(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    chunk_id: str,
    update_data: Dict[str, Any],
) -> Dict[str, Any]:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)

    normalized_update = update_data.copy()

    if "bounding_boxes" in normalized_update and normalized_update["bounding_boxes"] is not None:
        normalized_update["bounding_boxes"] = json.dumps(normalized_update["bounding_boxes"])

    normalized_update = SQLLocalService.add_processed_datetime_if_exists(table, normalized_update)

    with sql_local_service.Session() as session:
        stmt = update(table).where(table.c.chunk_id == chunk_id).values(**normalized_update)
        result = session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(f"Chunk with id='{chunk_id}' not found in table '{table_name}'")
        session.commit()

    return get_chunk_by_id(sql_local_service, schema_name, table_name, chunk_id)


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
