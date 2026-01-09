from typing import Iterator

import pytest
from sqlalchemy import select

from ada_backend.repositories.knowledge_repository import (
    delete_chunk,
    delete_document,
    list_documents_for_source,
)
from engine.storage_service.local_service import SQLLocalService
from ingestion_script.utils import UNIFIED_TABLE_DEFINITION
from tests.mocks.db_service import TEST_SCHEMA_NAME


@pytest.fixture
def sql_local_service(postgres_service: SQLLocalService) -> Iterator[SQLLocalService]:
    """Create knowledge_chunks table in the test schema."""
    postgres_service.create_table(
        table_name="knowledge_chunks",
        table_definition=UNIFIED_TABLE_DEFINITION,
        schema_name=TEST_SCHEMA_NAME,
    )

    yield postgres_service


def _insert_rows(service: SQLLocalService, rows: list[dict]) -> None:
    table = service.get_table(table_name="knowledge_chunks", schema_name=TEST_SCHEMA_NAME)
    with service.engine.begin() as conn:
        conn.execute(table.insert(), rows)


def test_list_documents_for_source_returns_grouped_data(sql_local_service: SQLLocalService) -> None:
    source_id = "00000000-0000-0000-0000-000000000001"
    _insert_rows(
        sql_local_service,
        [
            {
                "chunk_id": "c1",
                "source_id": source_id,
                "file_id": "file-a",
                "content": "alpha",
                "document_title": "Doc A",
                "url": "http://a",
                "last_edited_ts": "2024-01-01",
                "metadata": {"folder_name": "Folder"},
            },
            {
                "chunk_id": "c2",
                "source_id": source_id,
                "file_id": "file-a",
                "content": "beta",
                "document_title": "Doc A",
                "url": "http://a",
                "last_edited_ts": "2024-01-02",
                "metadata": {"folder_name": "Folder"},
            },
            {
                "chunk_id": "c3",
                "source_id": source_id,
                "file_id": "file-b",
                "content": "gamma",
                "document_title": "Doc B",
                "url": "http://b",
                "last_edited_ts": "2024-01-03",
                "metadata": {"folder_name": "Folder"},
            },
        ],
    )

    files = list_documents_for_source(
        sql_local_service=sql_local_service,
        schema_name=TEST_SCHEMA_NAME,
        table_name="knowledge_chunks",
        source_id=source_id,
    )

    assert len(files) == 2
    summary = {item.document_id: item for item in files}
    assert summary["file-a"].chunk_count == 2
    assert summary["file-b"].chunk_count == 1


def test_delete_document_removes_chunks(sql_local_service: SQLLocalService) -> None:
    source_id = "00000000-0000-0000-0000-000000000002"
    _insert_rows(
        sql_local_service,
        [
            {
                "chunk_id": "c1",
                "source_id": source_id,
                "file_id": "file-a",
                "content": "alpha",
                "document_title": "Doc",
                "url": "http://old",
                "last_edited_ts": "2024-01-01",
                "metadata": {"folder_name": "Folder"},
            }
        ],
    )

    deleted = delete_document(
        sql_local_service=sql_local_service,
        schema_name=TEST_SCHEMA_NAME,
        table_name="knowledge_chunks",
        document_id="file-a",
    )
    assert deleted is True

    table = sql_local_service.get_table(table_name="knowledge_chunks", schema_name=TEST_SCHEMA_NAME)
    with sql_local_service.engine.connect() as conn:
        remaining = conn.execute(select(table)).fetchall()
    assert remaining == []


def test_delete_document_returns_false_for_missing_document(sql_local_service: SQLLocalService) -> None:
    deleted = delete_document(
        sql_local_service=sql_local_service,
        schema_name=TEST_SCHEMA_NAME,
        table_name="knowledge_chunks",
        document_id="missing",
    )
    assert deleted is False


def test_delete_chunk_removes_row(sql_local_service: SQLLocalService) -> None:
    source_id = "00000000-0000-0000-0000-000000000003"
    _insert_rows(
        sql_local_service,
        [
            {
                "chunk_id": "c1",
                "source_id": source_id,
                "file_id": "file-a",
                "content": "content",
                "document_title": "Doc",
                "url": "http://url",
                "last_edited_ts": "2024-01-01",
                "metadata": {},
            }
        ],
    )

    delete_chunk(
        sql_local_service=sql_local_service,
        schema_name=TEST_SCHEMA_NAME,
        table_name="knowledge_chunks",
        chunk_id="c1",
        source_id=source_id,
    )


def test_delete_chunk_is_idempotent(sql_local_service: SQLLocalService) -> None:
    """Test that deleting a chunk multiple times is idempotent (second delete returns False)."""
    source_id = "00000000-0000-0000-0000-000000000004"
    _insert_rows(
        sql_local_service,
        [
            {
                "chunk_id": "c1",
                "source_id": source_id,
                "file_id": "file-a",
                "content": "content",
                "document_title": "Doc",
                "url": "http://url",
                "last_edited_ts": "2024-01-01",
                "metadata": {},
            }
        ],
    )

    # First delete should succeed
    deleted = delete_chunk(
        sql_local_service=sql_local_service,
        schema_name=TEST_SCHEMA_NAME,
        table_name="knowledge_chunks",
        chunk_id="c1",
        source_id=source_id,
    )
    assert deleted is True

    # second delete should succeed (return False)
    deleted = delete_chunk(
        sql_local_service=sql_local_service,
        schema_name=TEST_SCHEMA_NAME,
        table_name="knowledge_chunks",
        chunk_id="c1",
        source_id=source_id,
    )
    assert deleted is False
