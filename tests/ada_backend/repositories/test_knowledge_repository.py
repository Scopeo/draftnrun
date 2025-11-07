import json
from pathlib import Path
from typing import Iterator

import pytest
import sqlalchemy

from engine.storage_service.local_service import SQLLocalService
from ada_backend.repositories.knowledge_repository import (
    create_chunk,
    delete_chunk,
    delete_file,
    get_chunk_by_id,
    get_file_with_chunks,
    list_files_for_source,
    update_chunk,
    update_file_metadata,
)


@pytest.fixture
def sql_local_service(tmp_path: Path) -> Iterator[SQLLocalService]:
    db_path = tmp_path / "knowledge.sqlite"
    service = SQLLocalService(engine_url=f"sqlite:///{db_path}")
    metadata = sqlalchemy.MetaData()
    sqlalchemy.Table(
        "knowledge_chunks",
        metadata,
        sqlalchemy.Column("_processed_datetime", sqlalchemy.String, nullable=True),
        sqlalchemy.Column("chunk_id", sqlalchemy.String, primary_key=True),
        sqlalchemy.Column("file_id", sqlalchemy.String, nullable=False),
        sqlalchemy.Column("content", sqlalchemy.String, nullable=False),
        sqlalchemy.Column("document_title", sqlalchemy.String, nullable=True),
        sqlalchemy.Column("url", sqlalchemy.String, nullable=True),
        sqlalchemy.Column("last_edited_ts", sqlalchemy.String, nullable=True),
        sqlalchemy.Column("metadata", sqlalchemy.JSON, nullable=True),
        sqlalchemy.Column("bounding_boxes", sqlalchemy.String, nullable=True),
    )
    metadata.create_all(service.engine)
    service.metadata.reflect(bind=service.engine)
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


def test_update_file_metadata_updates_all_rows(sql_local_service: SQLLocalService) -> None:
    _insert_rows(
        sql_local_service,
        [
            {
                "chunk_id": "c1",
                "file_id": "file-a",
                "content": "alpha",
                "document_title": "Old",
                "url": "http://old",
                "last_edited_ts": "2024-01-01",
                "metadata": {"folder_name": "Folder"},
            },
            {
                "chunk_id": "c2",
                "file_id": "file-a",
                "content": "beta",
                "document_title": "Old",
                "url": "http://old",
                "last_edited_ts": "2024-01-02",
                "metadata": {"folder_name": "Folder"},
            },
        ],
    )

    update_file_metadata(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        file_id="file-a",
        document_title="Updated",
        url="http://new",
        metadata={"folder_name": "New"},
    )

    table = sql_local_service.get_table(table_name="knowledge_chunks", schema_name=None)
    with sql_local_service.engine.connect() as conn:
        rows = conn.execute(sqlalchemy.select(table)).fetchall()
    assert {row.document_title for row in rows} == {"Updated"}
    assert {row.url for row in rows} == {"http://new"}
    assert {row.metadata["folder_name"] for row in rows} == {"New"}


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
        remaining = conn.execute(sqlalchemy.select(table)).fetchall()
    assert remaining == []


def test_delete_file_raises_for_missing_file(sql_local_service: SQLLocalService) -> None:
    with pytest.raises(ValueError):
        delete_file(
            sql_local_service=sql_local_service,
            schema_name=None,
            table_name="knowledge_chunks",
            file_id="missing",
        )


def test_create_chunk_persists_row(sql_local_service: SQLLocalService) -> None:
    result = create_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
        file_id="file-a",
        content="some content",
        document_title="Doc",
        url="http://example.com",
        metadata={"folder_name": "Folder"},
        bounding_boxes=[{"page": 1}],
        last_edited_ts="2024-01-01",
    )

    assert result["chunk_id"] == "c1"
    assert result["metadata"] == {"folder_name": "Folder"}
    assert result["bounding_boxes"] == [{"page": 1}]


def test_create_chunk_raises_for_duplicate_id(sql_local_service: SQLLocalService) -> None:
    create_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
        file_id="file-a",
        content="some content",
        document_title=None,
        url=None,
        metadata=None,
        bounding_boxes=None,
        last_edited_ts="2024-01-01",
    )

    with pytest.raises(ValueError):
        create_chunk(
            sql_local_service=sql_local_service,
            schema_name=None,
            table_name="knowledge_chunks",
            chunk_id="c1",
            file_id="file-a",
            content="other",
            document_title=None,
            url=None,
            metadata=None,
            bounding_boxes=None,
            last_edited_ts="2024-01-02",
        )


def test_update_chunk_applies_changes(sql_local_service: SQLLocalService) -> None:
    create_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
        file_id="file-a",
        content="original",
        document_title="Original",
        url=None,
        metadata={"folder_name": "Folder"},
        bounding_boxes=[{"page": 1}],
        last_edited_ts="2024-01-01",
    )

    updated = update_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
        update_data={
            "content": "updated",
            "document_title": "Updated",
            "metadata": {"folder_name": "New"},
            "bounding_boxes": [{"page": 2}],
        },
    )

    assert updated["content"] == "updated"
    assert updated["document_title"] == "Updated"
    assert updated["metadata"] == {"folder_name": "New"}
    assert updated["bounding_boxes"] == [{"page": 2}]


def test_delete_chunk_removes_row(sql_local_service: SQLLocalService) -> None:
    create_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
        file_id="file-a",
        content="content",
        document_title=None,
        url=None,
        metadata=None,
        bounding_boxes=None,
        last_edited_ts="2024-01-01",
    )

    delete_chunk(
        sql_local_service=sql_local_service,
        schema_name=None,
        table_name="knowledge_chunks",
        chunk_id="c1",
    )

    with pytest.raises(ValueError):
        get_chunk_by_id(
            sql_local_service=sql_local_service,
            schema_name=None,
            table_name="knowledge_chunks",
            chunk_id="c1",
        )


def test_delete_chunk_raises_for_missing_chunk(sql_local_service: SQLLocalService) -> None:
    with pytest.raises(ValueError):
        delete_chunk(
            sql_local_service=sql_local_service,
            schema_name=None,
            table_name="knowledge_chunks",
            chunk_id="missing",
        )
