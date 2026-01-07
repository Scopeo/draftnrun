import logging
from typing import List, Tuple

from sqlalchemy import Table, delete, func, select
from sqlalchemy.engine import Row

from engine.storage_service.local_service import SQLLocalService

LOGGER = logging.getLogger(__name__)


def list_documents_for_source(
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
    source_id: str,
) -> List[Row]:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    # TODO: Change file_id to document_id
    stmt = (
        select(
            table.c.file_id.label("document_id"),
            func.max(table.c.document_title).label("document_title"),
            func.count().label("chunk_count"),
            func.max(table.c.last_edited_ts).label("last_edited_ts"),
        )
        .where(table.c.source_id == source_id)
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
    source_id: str,
) -> Tuple[List[Row], Table]:
    """Get all chunk rows for a given document_id, sorted by order. Returns (rows, table, total_count)."""
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    # TODO: Change file_id to document_id
    stmt = (
        select(table)
        .where(table.c.file_id == document_id)
        .where(table.c.source_id == source_id)
        .order_by(table.c.order.asc().nullslast())
    )

    with sql_local_service.execute_query(stmt) as (result, _):
        rows = result.fetchall()

    return rows, table


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
    source_id: str,
) -> bool:
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    stmt = delete(table).where(table.c.chunk_id == chunk_id).where(table.c.source_id == source_id)
    with sql_local_service.execute_query(stmt) as (result, _):
        if result.rowcount == 0:
            return False
        return True
