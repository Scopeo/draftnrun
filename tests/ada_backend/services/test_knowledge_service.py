from types import SimpleNamespace
from uuid import uuid4

import pytest

from ada_backend.services import knowledge_service
from ada_backend.schemas.knowledge_schema import (
    CreateKnowledgeChunkRequest,
    KnowledgeChunk,
    KnowledgeFileDetail,
    KnowledgeFileListResponse,
    KnowledgeFileMetadata,
    UpdateKnowledgeChunkRequest,
    UpdateKnowledgeFileRequest,
)


def _mock_source() -> SimpleNamespace:
    return SimpleNamespace(database_schema="schema", database_table_name="table")


def test_list_files_for_data_source_returns_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_args = {}

    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")

    def fake_list_files_for_source(**kwargs):
        captured_args.update(kwargs)
        return [
            {
                "file_id": "file-a",
                "document_title": "Doc",
                "chunk_count": 2,
                "last_edited_ts": "2024-01-02",
            }
        ]

    monkeypatch.setattr(knowledge_service, "list_files_for_source", fake_list_files_for_source)

    response = knowledge_service.list_files_for_data_source(
        session=None,
        organization_id=uuid4(),
        source_id=uuid4(),
    )

    assert isinstance(response, KnowledgeFileListResponse)
    assert response.total == 1
    assert response.items[0].file_id == "file-a"
    assert captured_args["schema_name"] == "schema"
    assert captured_args["table_name"] == "table"


def test_get_file_detail_for_data_source_returns_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")
    monkeypatch.setattr(
        knowledge_service,
        "get_file_with_chunks",
        lambda **_: {
            "file": {
                "file_id": "file-a",
                "document_title": "Doc",
                "url": "http://a",
                "metadata": {"folder_name": "Folder"},
                "last_edited_ts": "2024-01-02",
            },
            "chunks": [
                {
                    "chunk_id": "c1",
                    "file_id": "file-a",
                    "content": "alpha",
                    "document_title": "Doc",
                    "url": "http://a",
                    "last_edited_ts": "2024-01-02",
                    "metadata": {"folder_name": "Folder"},
                    "_processed_datetime": "2024-01-02T00:00:00",
                }
            ],
        },
    )

    detail = knowledge_service.get_file_detail_for_data_source(
        session=None,
        organization_id=uuid4(),
        source_id=uuid4(),
        file_id="file-a",
    )

    assert isinstance(detail, KnowledgeFileDetail)
    assert detail.file.file_id == "file-a"
    assert detail.chunks[0].processed_datetime == "2024-01-02T00:00:00"


def test_update_file_for_data_source_calls_update_and_returns_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {}

    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")

    def fake_update_file_metadata(**kwargs):
        called["update_kwargs"] = kwargs

    monkeypatch.setattr(knowledge_service, "update_file_metadata", fake_update_file_metadata)
    expected_detail = KnowledgeFileDetail(
        file=KnowledgeFileMetadata(
            file_id="file-a",
            document_title="Updated",
            url="http://new",
            metadata={},
        ),
        chunks=[],
    )

    def fake_get_file_detail_for_data_source(*args, **kwargs):
        called["detail_args"] = (args, kwargs)
        return expected_detail

    monkeypatch.setattr(knowledge_service, "get_file_detail_for_data_source", fake_get_file_detail_for_data_source)

    result = knowledge_service.update_file_for_data_source(
        session=None,
        organization_id=uuid4(),
        source_id=uuid4(),
        file_id="file-a",
        update_request=UpdateKnowledgeFileRequest(document_title="Updated"),
    )

    assert called["update_kwargs"]["document_title"] == "Updated"
    assert result.file.document_title == "Updated"


def test_delete_file_for_data_source_invokes_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {}
    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")

    def fake_delete_file(**kwargs):
        called["kwargs"] = kwargs

    monkeypatch.setattr(knowledge_service, "delete_file", fake_delete_file)

    knowledge_service.delete_file_for_data_source(
        session=None,
        organization_id=uuid4(),
        source_id=uuid4(),
        file_id="file-a",
    )

    assert called["kwargs"]["file_id"] == "file-a"


def test_list_files_for_data_source_raises_when_source_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: None)

    with pytest.raises(ValueError):
        knowledge_service.list_files_for_data_source(
            session=None,
            organization_id=uuid4(),
            source_id=uuid4(),
        )


def test_get_file_detail_for_data_source_raises_when_schema_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        knowledge_service,
        "get_data_source_by_org_id",
        lambda **_: SimpleNamespace(database_schema=None, database_table_name=None),
    )

    with pytest.raises(ValueError):
        knowledge_service.get_file_detail_for_data_source(
            session=None,
            organization_id=uuid4(),
            source_id=uuid4(),
            file_id="file-a",
        )


def test_create_chunk_for_data_source_returns_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    created = {
        "chunk_id": "c1",
        "file_id": "file-a",
        "content": "hello",
        "document_title": None,
        "url": None,
        "metadata": {},
        "bounding_boxes": None,
    }

    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")
    monkeypatch.setattr(knowledge_service, "file_exists", lambda *args, **kwargs: True)
    monkeypatch.setattr(knowledge_service, "_count_tokens", lambda _text: 10)
    monkeypatch.setattr(knowledge_service, "create_chunk", lambda **kwargs: created)

    request = CreateKnowledgeChunkRequest(content="hello")

    result = knowledge_service.create_chunk_for_data_source(
        session=None,
        organization_id=uuid4(),
        source_id=uuid4(),
        file_id="file-a",
        request=request,
    )

    assert isinstance(result, KnowledgeChunk)
    assert result.chunk_id == "c1"


def test_create_chunk_for_data_source_raises_when_file_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")
    monkeypatch.setattr(knowledge_service, "file_exists", lambda *args, **kwargs: False)

    with pytest.raises(ValueError):
        knowledge_service.create_chunk_for_data_source(
            session=None,
            organization_id=uuid4(),
            source_id=uuid4(),
            file_id="file-a",
            request=CreateKnowledgeChunkRequest(content="hello"),
        )


def test_create_chunk_for_data_source_enforces_token_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")
    monkeypatch.setattr(knowledge_service, "file_exists", lambda *args, **kwargs: True)
    monkeypatch.setattr(knowledge_service, "_count_tokens", lambda _text: 9000)

    with pytest.raises(ValueError):
        knowledge_service.create_chunk_for_data_source(
            session=None,
            organization_id=uuid4(),
            source_id=uuid4(),
            file_id="file-a",
            request=CreateKnowledgeChunkRequest(content="hello"),
        )


def test_update_chunk_for_data_source_returns_updated_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {}

    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")
    monkeypatch.setattr(
        knowledge_service,
        "get_chunk_by_id",
        lambda **_: {
            "chunk_id": "c1",
            "file_id": "file-a",
            "content": "hello",
            "document_title": None,
            "url": None,
            "metadata": {},
            "bounding_boxes": None,
        },
    )
    monkeypatch.setattr(knowledge_service, "_count_tokens", lambda _text: 100)

    def fake_update_chunk(**kwargs):
        called.update(kwargs)
        return {
            "chunk_id": "c1",
            "file_id": "file-a",
            "content": "updated",
            "document_title": "Doc",
            "url": None,
            "metadata": {"folder_name": "Folder"},
            "bounding_boxes": [{"page": 1}],
        }

    monkeypatch.setattr(knowledge_service, "update_chunk", fake_update_chunk)

    result = knowledge_service.update_chunk_for_data_source(
        session=None,
        organization_id=uuid4(),
        source_id=uuid4(),
        chunk_id="c1",
        request=UpdateKnowledgeChunkRequest(
            content="updated", document_title="Doc", metadata={"folder_name": "Folder"}, bounding_boxes=[{"page": 1}]
        ),
    )

    assert isinstance(result, KnowledgeChunk)
    assert result.content == "updated"
    assert called["chunk_id"] == "c1"
    assert "update_data" in called


def test_update_chunk_for_data_source_enforces_token_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")
    monkeypatch.setattr(
        knowledge_service,
        "get_chunk_by_id",
        lambda **_: {"chunk_id": "c1", "file_id": "file-a", "content": "hello"},
    )
    monkeypatch.setattr(knowledge_service, "_count_tokens", lambda _text: 9000)

    with pytest.raises(ValueError):
        knowledge_service.update_chunk_for_data_source(
            session=None,
            organization_id=uuid4(),
            source_id=uuid4(),
            chunk_id="c1",
            request=UpdateKnowledgeChunkRequest(content="updated"),
        )


def test_delete_chunk_for_data_source_invokes_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {}
    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **_: _mock_source())
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: "sql-service")

    def fake_delete_chunk(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(knowledge_service, "delete_chunk", fake_delete_chunk)

    knowledge_service.delete_chunk_for_data_source(
        session=None,
        organization_id=uuid4(),
        source_id=uuid4(),
        chunk_id="c1",
    )

    assert called["chunk_id"] == "c1"
