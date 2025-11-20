"""
Integration tests for knowledge service with real SQL and Qdrant connections.
Only the embedding service (LLM calls) is mocked.
"""

import asyncio
from typing import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import text

from ada_backend.services import knowledge_service
from ada_backend.schemas.knowledge_schema import (
    CreateKnowledgeChunkRequest,
    KnowledgeChunk,
    UpdateKnowledgeChunkRequest,
)
from ada_backend.repositories.knowledge_repository import get_chunk_by_id
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.storage_service.local_service import SQLLocalService
from engine.storage_service.db_utils import DBColumn, DBDefinition, PROCESSED_DATETIME_FIELD
from settings import settings
from tests.mocks.trace_manager import MockTraceManager

TEST_COLLECTION_NAME_PREFIX = "test_knowledge_v2"
EMBEDDING_SIZE = 3072


@pytest.fixture
def sql_local_service() -> Iterator[SQLLocalService]:
    """Create a real PostgreSQL connection to the ingestion database."""
    if not settings.INGESTION_DB_URL:
        pytest.skip("settings.INGESTION_DB_URL is not set. Cannot run integration tests without ingestion database.")

    try:
        service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
        yield service
    except Exception as e:
        raise e


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create a mock embedding service that returns fake embeddings."""
    mock_embedding = MagicMock(spec=EmbeddingService)
    mock_embedding.embedding_size = EMBEDDING_SIZE

    def create_fake_embedding_data(texts):
        """Create fake embedding data for a list of texts."""
        return [MagicMock(embedding=[0.1] * EMBEDDING_SIZE) for _ in texts]

    mock_embedding.embed_text_async = AsyncMock(side_effect=create_fake_embedding_data)
    return mock_embedding


@pytest.fixture
def qdrant_service(mock_embedding_service: MagicMock) -> Iterator[QdrantService]:
    """Create a real Qdrant service with mocked embedding service."""
    qdrant_schema = QdrantCollectionSchema(
        chunk_id_field="chunk_id",
        content_field="content",
        file_id_field="file_id",
        url_id_field="url",
        last_edited_ts_field="last_edited_ts",
        metadata_fields_to_keep={"metadata_to_keep_by_qdrant_field"},
    )
    qdrant_service = QdrantService.from_defaults(
        embedding_service=mock_embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )
    yield qdrant_service


@pytest.fixture
def test_collection_name() -> str:
    """Generate a unique test collection name."""
    return f"{TEST_COLLECTION_NAME_PREFIX}_{uuid4()}"


def _setup_test_table_and_collection_with_dummy_chunk(
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_collection_name: str,
) -> tuple[SimpleNamespace, str, str]:
    """
    Create a table and collection with a dummy chunk already in both SQL and Qdrant.
    Returns: (test_source, file_id, dummy_chunk_id)
    """
    source_id = uuid4()
    schema_name = f"test_knowledge_v2_{source_id.hex[:8]}"
    table_name = "knowledge_chunks"

    if not sql_local_service.schema_exists(schema_name):
        sql_local_service.create_schema(schema_name)

    table_definition = DBDefinition(
        columns=[
            DBColumn(name=PROCESSED_DATETIME_FIELD, type="STRING", default="CURRENT_TIMESTAMP", is_nullable=True),
            DBColumn(name="chunk_id", type="VARCHAR", is_primary_key=True),
            DBColumn(name="file_id", type="VARCHAR", is_nullable=False),
            DBColumn(name="content", type="VARCHAR", is_nullable=False),
            DBColumn(name="document_title", type="VARCHAR", is_nullable=True),
            DBColumn(name="url", type="VARCHAR", is_nullable=True),
            DBColumn(name="last_edited_ts", type="VARCHAR", is_nullable=True),
            DBColumn(name="metadata_to_keep_by_qdrant_field", type="VARCHAR", is_nullable=True),
            DBColumn(name="not_kept_by_qdrant_chunk_field", type="VARIANT", is_nullable=True),
        ]
    )

    if sql_local_service.table_exists(table_name, schema_name):
        sql_local_service.drop_table(table_name, schema_name)
    sql_local_service.create_table(
        table_name=table_name,
        table_definition=table_definition,
        schema_name=schema_name,
    )

    if asyncio.run(qdrant_service.collection_exists_async(test_collection_name)):
        asyncio.run(qdrant_service.delete_collection_async(test_collection_name))
    asyncio.run(qdrant_service.create_collection_async(collection_name=test_collection_name))

    file_id = f"test_file_{uuid4()}"
    dummy_chunk_id = str(uuid4())

    # Insert directly into SQL table with explicit non-default values
    table = sql_local_service.get_table(table_name=table_name, schema_name=schema_name)
    with sql_local_service.Session() as session:
        insert_data = {
            "chunk_id": dummy_chunk_id,
            "file_id": file_id,
            "content": "Dummy chunk content",
            "last_edited_ts": "2024-01-01T00:00:00",
            "url": "http://example.com/dummy",
            "document_title": "Dummy Document",
            "metadata_to_keep_by_qdrant_field": "dummy_metadata_value",
            "not_kept_by_qdrant_chunk_field": {"key": "value"},
        }
        session.execute(table.insert(), insert_data)
        session.commit()

    chunk_dict = {
        "chunk_id": dummy_chunk_id,
        "file_id": file_id,
        "content": "Dummy chunk content",
        "last_edited_ts": "2024-01-01T00:00:00",
        "url": "http://example.com/dummy",
        "metadata_to_keep_by_qdrant_field": "dummy_metadata_value",
    }
    asyncio.run(qdrant_service.add_chunks_async(list_chunks=[chunk_dict], collection_name=test_collection_name))

    source = SimpleNamespace(
        id=source_id,
        database_schema=schema_name,
        database_table_name=table_name,
        qdrant_collection_name=test_collection_name,
        qdrant_schema={
            "chunk_id_field": "chunk_id",
            "content_field": "content",
            "file_id_field": "file_id",
            "url_id_field": "url",
            "last_edited_ts_field": "last_edited_ts",
            "metadata_fields_to_keep": ["metadata_to_keep_by_qdrant_field"],
            "metadata_field_types": {"metadata_to_keep_by_qdrant_field": "VARCHAR"},
        },
        embedding_model_reference="openai:text-embedding-3-large",
    )

    return source, file_id, dummy_chunk_id


def _setup_test_environment(
    monkeypatch: pytest.MonkeyPatch,
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_collection_name: str,
) -> tuple[SimpleNamespace, str, str]:
    """
    Setup test environment with monkeypatch and test source.
    Returns: (test_source, file_id, dummy_chunk_id)
    """
    mock_trace_manager = MockTraceManager(project_name="test")
    monkeypatch.setattr(knowledge_service, "get_trace_manager", lambda: mock_trace_manager)

    test_source, file_id, dummy_chunk_id = _setup_test_table_and_collection_with_dummy_chunk(
        sql_local_service, qdrant_service, test_collection_name
    )

    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **kwargs: test_source)
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: sql_local_service)

    return test_source, file_id, dummy_chunk_id


def _verify_dummy_chunk_unchanged(
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_source: SimpleNamespace,
    dummy_chunk_id: str,
) -> None:
    """
    Verify that the dummy chunk still exists in both SQL and Qdrant with unchanged content.

    Args:
        sql_local_service: SQL service instance
        qdrant_service: Qdrant service instance
        test_source: Test source configuration
        dummy_chunk_id: ID of the dummy chunk to verify
    """
    collection_data = asyncio.run(qdrant_service.get_collection_data_async(test_source.qdrant_collection_name))
    chunk_ids = collection_data["chunk_id"].tolist()
    assert len(chunk_ids) == 1
    assert dummy_chunk_id in chunk_ids

    qdrant_chunk = collection_data[collection_data["chunk_id"] == dummy_chunk_id].iloc[0]
    assert qdrant_chunk["content"] == "Dummy chunk content"

    sql_chunk = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=test_source.database_schema,
        table_name=test_source.database_table_name,
        chunk_id=dummy_chunk_id,
    )
    assert sql_chunk["chunk_id"] == dummy_chunk_id
    assert sql_chunk["content"] == "Dummy chunk content"


def _cleanup_test_environment(
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_source: SimpleNamespace,
) -> None:
    """Clean up test environment (drop table, schema, and Qdrant collection)."""
    try:
        if sql_local_service.table_exists(test_source.database_table_name, test_source.database_schema):
            sql_local_service.drop_table(test_source.database_table_name, test_source.database_schema)
        with sql_local_service.engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {test_source.database_schema} CASCADE"))
            conn.commit()
    except Exception as e:
        print(f"Warning: Failed to cleanup schema {test_source.database_schema}: {e}")

    if asyncio.run(qdrant_service.collection_exists_async(test_source.qdrant_collection_name)):
        asyncio.run(qdrant_service.delete_collection_async(test_source.qdrant_collection_name))


def test_chunk_operations_integration(
    monkeypatch: pytest.MonkeyPatch,
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_collection_name: str,
) -> None:
    """Test create, update, and delete chunk operations with real SQL and Qdrant operations."""
    test_source, file_id, dummy_chunk_id = _setup_test_environment(
        monkeypatch, sql_local_service, qdrant_service, test_collection_name
    )

    # ========== TEST CREATE CHUNK ==========
    new_chunk_content = "This is test chunk content for integration testing."

    create_request = CreateKnowledgeChunkRequest(
        content=new_chunk_content,
    )

    mock_session = Mock()
    create_result = knowledge_service.create_chunk_for_data_source(
        session=mock_session,
        organization_id=uuid4(),
        source_id=test_source.id,
        file_id=file_id,
        request=create_request,
    )

    assert isinstance(create_result, KnowledgeChunk)
    assert create_result.content == new_chunk_content

    sql_chunk = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=test_source.database_schema,
        table_name=test_source.database_table_name,
        chunk_id=create_result.chunk_id,
    )
    assert sql_chunk["chunk_id"] == create_result.chunk_id
    assert sql_chunk["content"] == new_chunk_content
    # Check that metadata_to_keep_by_qdrant_field is in the DB with default value
    assert "metadata_to_keep_by_qdrant_field" in sql_chunk
    assert sql_chunk["metadata_to_keep_by_qdrant_field"] == ""
    # Check that not_kept_by_qdrant_chunk_field is in the DB with default value (VARIANT type should be {})
    assert "not_kept_by_qdrant_chunk_field" in sql_chunk
    assert sql_chunk["not_kept_by_qdrant_chunk_field"] == {}

    collection_data = asyncio.run(qdrant_service.get_collection_data_async(test_source.qdrant_collection_name))
    chunk_ids = collection_data["chunk_id"].tolist()
    assert create_result.chunk_id in chunk_ids

    qdrant_chunk = collection_data[collection_data["chunk_id"] == create_result.chunk_id].iloc[0]
    assert qdrant_chunk["content"] == new_chunk_content
    assert qdrant_chunk["url"] == ""
    # Check that metadata_to_keep_by_qdrant_field was added with default value (empty string for VARCHAR)
    assert "metadata_to_keep_by_qdrant_field" in qdrant_chunk
    assert qdrant_chunk["metadata_to_keep_by_qdrant_field"] == ""

    assert dummy_chunk_id in chunk_ids

    # ========== TEST UPDATE CHUNK ==========
    # Capture state before update
    sql_chunk_before = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=test_source.database_schema,
        table_name=test_source.database_table_name,
        chunk_id=create_result.chunk_id,
    )
    collection_data_before = asyncio.run(qdrant_service.get_collection_data_async(test_source.qdrant_collection_name))
    qdrant_chunk_before = collection_data_before[collection_data_before["chunk_id"] == create_result.chunk_id].iloc[0]

    updated_content = "Updated chunk content"

    update_request = UpdateKnowledgeChunkRequest(
        content=updated_content,
    )

    update_result = knowledge_service.update_chunk_for_data_source(
        session=mock_session,
        organization_id=uuid4(),
        source_id=test_source.id,
        chunk_id=create_result.chunk_id,
        request=update_request,
    )

    assert isinstance(update_result, KnowledgeChunk)
    assert update_result.content == updated_content

    # Verify SQL chunk after update
    sql_chunk_after = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=test_source.database_schema,
        table_name=test_source.database_table_name,
        chunk_id=create_result.chunk_id,
    )
    assert sql_chunk_after["chunk_id"] == create_result.chunk_id
    assert sql_chunk_after["content"] == updated_content

    # Verify Qdrant chunk after update
    collection_data_after = asyncio.run(qdrant_service.get_collection_data_async(test_source.qdrant_collection_name))
    chunk_ids = collection_data_after["chunk_id"].tolist()
    assert create_result.chunk_id in chunk_ids

    qdrant_chunk_after = collection_data_after[collection_data_after["chunk_id"] == create_result.chunk_id].iloc[0]
    assert qdrant_chunk_after["content"] == updated_content

    # Verify that only updated fields changed, all other fields remain the same
    # Fields that should have changed: content, last_edited_ts
    assert sql_chunk_after["content"] != sql_chunk_before["content"]
    assert sql_chunk_after["last_edited_ts"] != sql_chunk_before["last_edited_ts"]
    assert qdrant_chunk_after["content"] != qdrant_chunk_before["content"]
    assert qdrant_chunk_after["last_edited_ts"] != qdrant_chunk_before["last_edited_ts"]

    # Fields that should remain the same in SQL
    assert sql_chunk_after["chunk_id"] == sql_chunk_before["chunk_id"]
    assert sql_chunk_after["file_id"] == sql_chunk_before["file_id"]
    assert sql_chunk_after["url"] == sql_chunk_before["url"]
    assert sql_chunk_after["metadata_to_keep_by_qdrant_field"] == sql_chunk_before["metadata_to_keep_by_qdrant_field"]
    assert sql_chunk_after["not_kept_by_qdrant_chunk_field"] == sql_chunk_before["not_kept_by_qdrant_chunk_field"]

    # Fields that should remain the same in Qdrant
    assert qdrant_chunk_after["chunk_id"] == qdrant_chunk_before["chunk_id"]
    assert qdrant_chunk_after["file_id"] == qdrant_chunk_before["file_id"]
    assert qdrant_chunk_after["url"] == qdrant_chunk_before["url"]
    assert (
        qdrant_chunk_after["metadata_to_keep_by_qdrant_field"]
        == qdrant_chunk_before["metadata_to_keep_by_qdrant_field"]
    )

    # ========== TEST DELETE CHUNK ==========
    initial_collection_data = asyncio.run(qdrant_service.get_collection_data_async(test_source.qdrant_collection_name))
    initial_chunk_ids = initial_collection_data["chunk_id"].tolist()
    assert create_result.chunk_id in initial_chunk_ids
    initial_count = len(initial_chunk_ids)

    # Delete chunk
    knowledge_service.delete_chunk_for_data_source(
        session=mock_session,
        organization_id=uuid4(),
        source_id=test_source.id,
        chunk_id=create_result.chunk_id,
    )

    # Verify SQL database - chunk should be deleted
    with pytest.raises(ValueError, match="not found"):
        get_chunk_by_id(
            sql_local_service=sql_local_service,
            schema_name=test_source.database_schema,
            table_name=test_source.database_table_name,
            chunk_id=create_result.chunk_id,
        )

    final_collection_data = asyncio.run(qdrant_service.get_collection_data_async(test_source.qdrant_collection_name))
    final_chunk_ids = final_collection_data["chunk_id"].tolist()
    assert create_result.chunk_id not in final_chunk_ids
    final_count = len(final_chunk_ids)
    assert final_count == initial_count - 1

    assert dummy_chunk_id in final_chunk_ids

    _cleanup_test_environment(sql_local_service, qdrant_service, test_source)


def test_create_chunk_raises_when_zero_tokens(
    monkeypatch: pytest.MonkeyPatch,
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_collection_name: str,
) -> None:
    """Test that creating a chunk with zero tokens raises ValueError."""
    test_source, file_id, dummy_chunk_id = _setup_test_environment(
        monkeypatch, sql_local_service, qdrant_service, test_collection_name
    )
    monkeypatch.setattr(knowledge_service, "_count_tokens", lambda _text: 0)

    request = CreateKnowledgeChunkRequest(content="")
    mock_session = Mock()

    with pytest.raises(ValueError, match="zero tokens"):
        knowledge_service.create_chunk_for_data_source(
            session=mock_session,
            organization_id=uuid4(),
            source_id=test_source.id,
            file_id=file_id,
            request=request,
        )

    _verify_dummy_chunk_unchanged(sql_local_service, qdrant_service, test_source, dummy_chunk_id)
    _cleanup_test_environment(sql_local_service, qdrant_service, test_source)


def test_create_chunk_raises_when_exceeds_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_collection_name: str,
) -> None:
    """Test that creating a chunk exceeding max tokens raises ValueError."""
    test_source, file_id, dummy_chunk_id = _setup_test_environment(
        monkeypatch, sql_local_service, qdrant_service, test_collection_name
    )
    monkeypatch.setattr(knowledge_service, "_count_tokens", lambda _text: 9000)

    request = CreateKnowledgeChunkRequest(content="Very long content...")
    mock_session = Mock()

    with pytest.raises(ValueError, match="exceeds maximum allowed token count"):
        knowledge_service.create_chunk_for_data_source(
            session=mock_session,
            organization_id=uuid4(),
            source_id=test_source.id,
            file_id=file_id,
            request=request,
        )

    _verify_dummy_chunk_unchanged(sql_local_service, qdrant_service, test_source, dummy_chunk_id)
    _cleanup_test_environment(sql_local_service, qdrant_service, test_source)


def test_update_chunk_raises_when_zero_tokens(
    monkeypatch: pytest.MonkeyPatch,
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_collection_name: str,
) -> None:
    """Test that updating a chunk to zero tokens raises ValueError."""
    test_source, file_id, dummy_chunk_id = _setup_test_environment(
        monkeypatch, sql_local_service, qdrant_service, test_collection_name
    )
    monkeypatch.setattr(knowledge_service, "_count_tokens", lambda _text: 0)

    request = UpdateKnowledgeChunkRequest(content="")
    mock_session = Mock()

    with pytest.raises(ValueError, match="zero tokens"):
        knowledge_service.update_chunk_for_data_source(
            session=mock_session,
            organization_id=uuid4(),
            source_id=test_source.id,
            chunk_id=dummy_chunk_id,
            request=request,
        )

    _verify_dummy_chunk_unchanged(sql_local_service, qdrant_service, test_source, dummy_chunk_id)
    _cleanup_test_environment(sql_local_service, qdrant_service, test_source)


def test_update_chunk_raises_when_exceeds_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_collection_name: str,
) -> None:
    """Test that updating a chunk exceeding max tokens raises ValueError."""
    test_source, file_id, dummy_chunk_id = _setup_test_environment(
        monkeypatch, sql_local_service, qdrant_service, test_collection_name
    )
    monkeypatch.setattr(knowledge_service, "_count_tokens", lambda _text: 9000)

    request = UpdateKnowledgeChunkRequest(content="Very long content...")
    mock_session = Mock()

    with pytest.raises(ValueError, match="exceeds maximum allowed token count"):
        knowledge_service.update_chunk_for_data_source(
            session=mock_session,
            organization_id=uuid4(),
            source_id=test_source.id,
            chunk_id=dummy_chunk_id,
            request=request,
        )

    _verify_dummy_chunk_unchanged(sql_local_service, qdrant_service, test_source, dummy_chunk_id)
    _cleanup_test_environment(sql_local_service, qdrant_service, test_source)


def test_create_chunk_raises_when_file_not_exists(
    monkeypatch: pytest.MonkeyPatch,
    sql_local_service: SQLLocalService,
    qdrant_service: QdrantService,
    test_collection_name: str,
) -> None:
    """Test that creating a chunk for non-existent file raises ValueError."""
    test_source, file_id, dummy_chunk_id = _setup_test_environment(
        monkeypatch, sql_local_service, qdrant_service, test_collection_name
    )

    request = CreateKnowledgeChunkRequest(content="Test content")
    mock_session = Mock()

    with pytest.raises(ValueError, match="not found"):
        knowledge_service.create_chunk_for_data_source(
            session=mock_session,
            organization_id=uuid4(),
            source_id=test_source.id,
            file_id="non_existent_file",
            request=request,
        )

    _verify_dummy_chunk_unchanged(sql_local_service, qdrant_service, test_source, dummy_chunk_id)
    _cleanup_test_environment(sql_local_service, qdrant_service, test_source)


def test_validate_qdrant_service_raises_when_missing_collection_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that missing qdrant_collection_name raises ValueError."""
    source = SimpleNamespace(
        id=uuid4(),
        database_schema="schema",
        database_table_name="table",
        qdrant_collection_name=None,
        qdrant_schema={
            "chunk_id_field": "chunk_id",
            "content_field": "content",
            "file_id_field": "file_id",
            "url_id_field": "url",
            "last_edited_ts_field": "last_edited_ts",
        },
        embedding_model_reference="openai:text-embedding-3-large",
    )

    with pytest.raises(ValueError, match="missing qdrant_collection_name"):
        knowledge_service._validate_and_get_qdrant_service(source)


def test_validate_qdrant_service_raises_when_collection_not_exists(
    monkeypatch: pytest.MonkeyPatch,
    qdrant_service: QdrantService,
) -> None:
    """Test that non-existent Qdrant collection raises ValueError."""
    mock_trace_manager = MockTraceManager(project_name="test")
    monkeypatch.setattr(knowledge_service, "get_trace_manager", lambda: mock_trace_manager)

    non_existent_collection = f"non_existent_{uuid4()}"
    source = SimpleNamespace(
        id=uuid4(),
        database_schema="schema",
        database_table_name="table",
        qdrant_collection_name=non_existent_collection,
        qdrant_schema={
            "chunk_id_field": "chunk_id",
            "content_field": "content",
            "file_id_field": "file_id",
            "url_id_field": "url",
            "last_edited_ts_field": "last_edited_ts",
        },
        embedding_model_reference="openai:text-embedding-3-large",
    )

    with pytest.raises(ValueError, match="does not exist"):
        knowledge_service._validate_and_get_qdrant_service(source)


def test_validate_qdrant_service_raises_when_invalid_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that invalid qdrant_schema raises ValueError."""
    source = SimpleNamespace(
        id=uuid4(),
        database_schema="schema",
        database_table_name="table",
        qdrant_collection_name="test_collection",
        qdrant_schema={"invalid": "schema"},
        embedding_model_reference="openai:text-embedding-3-large",
    )

    with pytest.raises(ValueError, match="invalid qdrant_schema"):
        knowledge_service._validate_and_get_qdrant_service(source)


def test_validate_qdrant_service_raises_when_invalid_embedding_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that invalid embedding_model_reference raises ValueError."""
    source = SimpleNamespace(
        id=uuid4(),
        database_schema="schema",
        database_table_name="table",
        qdrant_collection_name="test_collection",
        qdrant_schema={
            "chunk_id_field": "chunk_id",
            "content_field": "content",
            "file_id_field": "file_id",
            "url_id_field": "url",
            "last_edited_ts_field": "last_edited_ts",
        },
        embedding_model_reference="invalid_format",
    )

    with pytest.raises(ValueError, match="invalid embedding_model_reference"):
        knowledge_service._validate_and_get_qdrant_service(source)
