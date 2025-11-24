import json
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import select

from engine.storage_service.local_service import SQLLocalService
from engine.storage_service.db_utils import DBDefinition, DBColumn, PROCESSED_DATETIME_FIELD
from ada_backend.repositories.knowledge_repository import (
    create_chunk,
    delete_chunk,
    delete_file,
    get_chunk_by_id,
    get_file_with_chunks,
    list_files_for_source,
    update_chunk,
)
from ada_backend.schemas.knowledge_schema import KnowledgeChunk
from ada_backend.services.knowledge.errors import (
    KnowledgeServiceChunkNotFoundError,
    KnowledgeServiceChunkAlreadyExistsError,
    KnowledgeServiceFileNotFoundError,
)


@pytest.fixture
def sql_local_service(tmp_path: Path) -> Iterator[SQLLocalService]:
    db_path = tmp_path / "knowledge.sqlite"
    service = SQLLocalService(engine_url=f"sqlite:///{db_path}")

    table_definition = DBDefinition(
        columns=[
            DBColumn(name=PROCESSED_DATETIME_FIELD, type="VARCHAR", is_nullable=True),
            DBColumn(name="chunk_id", type="VARCHAR", is_primary_key=True),
            DBColumn(name="file_id", type="VARCHAR", is_nullable=False),
            DBColumn(name="content", type="VARCHAR", is_nullable=False),
            DBColumn(name="document_title", type="VARCHAR", is_nullable=True),
            DBColumn(name="url", type="VARCHAR", is_nullable=True),
            DBColumn(name="last_edited_ts", type="VARCHAR", is_nullable=True),
            DBColumn(name="metadata", type="VARIANT", is_nullable=True),
            DBColumn(name="bounding_boxes", type="VARCHAR", is_nullable=True),
        ]
    )

    service.create_table(
        table_name="knowledge_chunks",
        table_definition=table_definition,
        schema_name=None,
    )

    yield service


def _insert_rows(service: SQLLocalService, rows: list[dict]) -> None:
    table = service.get_table(table_name="knowledge_chunks", schema_name=None)
    with service.engine.begin() as conn:
        conn.execute(table.insert(), rows)


def test_list_files_for_source_returns_grouped_data(sql_local_service: SQLLocalService) -> None:
    _insert_rows(
        sql_local_service,
        [
            {
                "chunk_id": "c1",
                "file_id": "file-a",
                "content": "alpha",
                "document_title": "Doc A",
                "url": "http://a",
                "last_edited_ts": "2024-01-01",
                "metadata": {"folder_name": "Folder"},
            },
            {
                "chunk_id": "c2",
                "file_id": "file-a",
                "content": "beta",
                "document_title": "Doc A",
                "url": "http://a",
                "last_edited_ts": "2024-01-02",
                "metadata": {"folder_name": "Folder"},
            },
            {
                "chunk_id": "c3",
                "file_id": "file-b",
                "content": "gamma",
                "document_title": "Doc B",
                "url": "http://b",
                "last_edited_ts": "2024-01-03",
                "metadata": {"folder_name": "Folder"},
            },
        ],
    )

    files = list_files_for_source(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
    )

    assert len(files) == 2
    summary = {item["file_id"]: item for item in files}
    assert summary["file-a"]["chunk_count"] == 2
    assert summary["file-b"]["chunk_count"] == 1


def test_get_file_with_chunks_returns_deserialized_metadata(sql_local_service: SQLLocalService) -> None:
    bounding_boxes = json.dumps([{"page": 1}])
    _insert_rows(
        sql_local_service,
        [
            {
                "chunk_id": "c1",
                "file_id": "file-a",
                "content": "alpha",
                "document_title": "Doc A",
                "url": "http://a",
                "last_edited_ts": "2024-01-02",
                "metadata": {"folder_name": "Folder"},
                "bounding_boxes": bounding_boxes,
            }
        ],
    )

    payload = get_file_with_chunks(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        file_id="file-a",
    )

    assert payload["file"]["document_title"] == "Doc A"
    assert payload["file"]["folder_name"] == "Folder"
    assert payload["chunks"][0]["metadata"] == {"folder_name": "Folder"}
    assert payload["chunks"][0]["bounding_boxes"] == [{"page": 1}]


def test_delete_file_removes_chunks(sql_local_service: SQLLocalService) -> None:
    _insert_rows(
        sql_local_service,
        [
            {
                "chunk_id": "c1",
                "file_id": "file-a",
                "content": "alpha",
                "document_title": "Doc",
                "url": "http://old",
                "last_edited_ts": "2024-01-01",
                "metadata": {"folder_name": "Folder"},
            }
        ],
    )

    delete_file(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        file_id="file-a",
    )

    table = sql_local_service.get_table(table_name="knowledge_chunks", schema_name=None)
    with sql_local_service.engine.connect() as conn:
        remaining = conn.execute(select(table)).fetchall()
    assert remaining == []


def test_delete_file_raises_for_missing_file(sql_local_service: SQLLocalService) -> None:
    with pytest.raises(KnowledgeServiceFileNotFoundError):
        delete_file(
            sql_local_service=sql_local_service,
            schema_name=None,
            table_name="knowledge_chunks",
            file_id="missing",
        )


def test_create_chunk_persists_row(sql_local_service: SQLLocalService) -> None:
    chunk = KnowledgeChunk(
        chunk_id="c1",
        file_id="file-a",
        content="some content",
        last_edited_ts="2024-01-01",
    )
    create_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk=chunk,
    )

    persisted_chunk = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
    )

    assert persisted_chunk["chunk_id"] == "c1"
    assert persisted_chunk["content"] == "some content"
    assert persisted_chunk["file_id"] == "file-a"
    assert persisted_chunk["last_edited_ts"] == "2024-01-01"


def test_create_chunk_raises_for_duplicate_id(sql_local_service: SQLLocalService) -> None:
    chunk1 = KnowledgeChunk(
        chunk_id="c1",
        file_id="file-a",
        content="some content",
        last_edited_ts="2024-01-01",
    )
    create_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk=chunk1,
    )

    chunk2 = KnowledgeChunk(
        chunk_id="c1",
        file_id="file-a",
        content="other",
        last_edited_ts="2024-01-02",
    )
    with pytest.raises(KnowledgeServiceChunkAlreadyExistsError):
        create_chunk(
            sql_local_service=sql_local_service,
            schema_name=None,
            table_name="knowledge_chunks",
            chunk=chunk2,
        )


def test_update_chunk_applies_changes(sql_local_service: SQLLocalService) -> None:
    chunk = KnowledgeChunk(
        chunk_id="c1",
        file_id="file-a",
        content="original",
        last_edited_ts="2024-01-01",
    )
    create_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk=chunk,
    )

    initial_chunk = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
    )
    assert initial_chunk["content"] == "original"
    assert initial_chunk["last_edited_ts"] == "2024-01-01"

    updated_chunk = KnowledgeChunk(
        chunk_id="c1",
        file_id="file-a",
        content="updated",
        last_edited_ts="2024-01-02",
    )
    update_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk=updated_chunk,
    )

    persisted_chunk = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
    )

    assert persisted_chunk["content"] == "updated"
    assert persisted_chunk["last_edited_ts"] == "2024-01-02"
    assert persisted_chunk["chunk_id"] == "c1"
    assert persisted_chunk["file_id"] == "file-a"


def test_delete_chunk_removes_row(sql_local_service: SQLLocalService) -> None:
    chunk = KnowledgeChunk(
        chunk_id="c1",
        file_id="file-a",
        content="content",
        last_edited_ts="2024-01-01",
    )
    create_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk=chunk,
    )

    delete_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
    )

    with pytest.raises(KnowledgeServiceChunkNotFoundError):
        get_chunk_by_id(
            sql_local_service=sql_local_service,
            schema_name=None,
            table_name="knowledge_chunks",
            chunk_id="c1",
        )


def test_delete_chunk_raises_for_missing_chunk(sql_local_service: SQLLocalService) -> None:
    with pytest.raises(KnowledgeServiceChunkNotFoundError):
        delete_chunk(
            sql_local_service=sql_local_service,
            schema_name=None,
            table_name="knowledge_chunks",
            chunk_id="missing",
        )


def test_delete_chunk_is_idempotent(sql_local_service: SQLLocalService) -> None:
    """Test that deleting a chunk multiple times is idempotent (second delete raises error)."""
    chunk = KnowledgeChunk(
        chunk_id="c1",
        file_id="file-a",
        content="content",
        last_edited_ts="2024-01-01",
    )
    create_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk=chunk,
    )

    # First delete should succeed
    delete_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
    )

    # Second delete should raise error (chunk not found)
    with pytest.raises(KnowledgeServiceChunkNotFoundError):
        delete_chunk(
            sql_local_service=sql_local_service,
            schema_name=None,
            table_name="knowledge_chunks",
            chunk_id="c1",
        )
