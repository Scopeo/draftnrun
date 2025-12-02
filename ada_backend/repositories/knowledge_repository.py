import logging
from typing import Any, Dict, List

from sqlalchemy import func, select, delete

from engine.storage_service.local_service import SQLLocalService


LOGGER = logging.getLogger(__name__)


def list_documents_for_source(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
) -> List[Dict[str, Any]]:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    # TODO: Change file_id to document_id
    stmt = (
        select(
            table.c.file_id.label("document_id"),
            func.max(table.c.document_title).label("document_title"),
            func.count().label("chunk_count"),
            func.max(table.c.last_edited_ts).label("last_edited_ts"),
        )
        .group_by(table.c.file_id)
        .order_by(func.max(table.c.last_edited_ts).desc())
    )
    with sql_local_service.execute_query(stmt) as (result, _):
        rows = result.all()
    return rows


def get_chunk_rows_for_document(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    document_id: str,
    limit: int = None,
    offset: int = None,
) -> tuple:
    """Get all chunk rows for a given document_id, sorted by chunk_id. Returns (rows, table, total_count)."""
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    # TODO: Change file_id to document_id
    count_stmt = select(func.count()).select_from(table).where(table.c.file_id == document_id)

    stmt = select(table).where(table.c.file_id == document_id).order_by(table.c.chunk_id)

    if limit is not None:
        stmt = stmt.limit(limit)
    if offset is not None:
        stmt = stmt.offset(offset)

    with sql_local_service.execute_query(count_stmt) as (result, _):
        total_count = result.scalar()

    with sql_local_service.execute_query(stmt) as (result, connection):
        rows = result.fetchall()

    return rows, table, total_count


def delete_document(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    document_id: str,
) -> bool:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    # TODO: Change file_id to document_id
    stmt = delete(table).where(table.c.file_id == document_id)
    with sql_local_service.execute_query(stmt) as (result, connection):
        if result.rowcount == 0:
            return False
        return True


def delete_chunk(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    chunk_id: str,
) -> bool:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    stmt = delete(table).where(table.c.chunk_id == chunk_id)
    with sql_local_service.execute_query(stmt) as (result, _):
        if result.rowcount == 0:
            return False
        return True
