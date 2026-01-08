"""
Integration tests for knowledge service with real SQL connections.
Qdrant and embedding service (LLM calls) are mocked.
"""

import asyncio
import logging
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import text

from ada_backend.services import knowledge_service
from ada_backend.services.knowledge.errors import (
    KnowledgeServiceInvalidEmbeddingModelReferenceError,
    KnowledgeServiceInvalidQdrantSchemaError,
    KnowledgeServiceQdrantCollectionNotFoundError,
)
from engine.llm_services.llm_service import EmbeddingService
from engine.storage_service.local_service import SQLLocalService
from ingestion_script.ingest_folder_source import FILE_TABLE_DEFINITION
from settings import settings
from tests.mocks.qdrant_service import mock_qdrant_service as _mock_qdrant_service
from tests.mocks.trace_manager import MockTraceManager

TEST_COLLECTION_NAME_PREFIX = "test_knowledge"
EMBEDDING_SIZE = 3072

LOGGER = logging.getLogger(__name__)

# Re-export as pytest fixture
mock_qdrant_service = pytest.fixture(_mock_qdrant_service)


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
def test_collection_name() -> str:
    """Generate a unique test collection name."""
    return f"{TEST_COLLECTION_NAME_PREFIX}_{uuid4()}"


def _setup_test_table_and_collection_with_dummy_chunk(
    sql_local_service: SQLLocalService,
    mock_qdrant_service: MagicMock,
    test_collection_name: str,
) -> tuple[SimpleNamespace, str, str]:
    """
    Create a table and collection with a dummy chunk already in both SQL and mocked Qdrant.
    Returns: (test_source, file_id, dummy_chunk_id)
    """
    source_id = uuid4()
    schema_name = f"test_knowledge_v2_{source_id.hex[:8]}"
    table_name = "knowledge_chunks"

    if not sql_local_service.schema_exists(schema_name):
        sql_local_service.create_schema(schema_name)

    if sql_local_service.table_exists(table_name, schema_name):
        sql_local_service.drop_table(table_name, schema_name)
    sql_local_service.create_table(
        table_name=table_name,
        table_definition=FILE_TABLE_DEFINITION,
        schema_name=schema_name,
    )

    # Setup mock Qdrant collection
    mock_qdrant_service.create_collection(collection_name=test_collection_name)

    file_id = f"test_file_{uuid4()}"
    dummy_chunk_id = f"{file_id}_1"

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
    mock_qdrant_service.add_chunks(list_chunks=[chunk_dict], collection_name=test_collection_name)

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
    mock_qdrant_service: MagicMock,
    test_collection_name: str,
) -> tuple[SimpleNamespace, str, str]:
    """
    Setup test environment with monkeypatch and test source.
    Returns: (test_source, file_id, dummy_chunk_id)
    """
    mock_trace_manager = MockTraceManager(project_name="test")
    monkeypatch.setattr(knowledge_service, "get_trace_manager", lambda: mock_trace_manager)

    test_source, file_id, dummy_chunk_id = _setup_test_table_and_collection_with_dummy_chunk(
        sql_local_service, mock_qdrant_service, test_collection_name
    )

    monkeypatch.setattr(knowledge_service, "get_data_source_by_org_id", lambda **kwargs: test_source)
    monkeypatch.setattr(knowledge_service, "get_sql_local_service_for_ingestion", lambda: sql_local_service)

    # Mock _get_qdrant_service to return our mock
    def _get_qdrant_service_mock(qdrant_schema, embedding_model_reference):
        return mock_qdrant_service

    monkeypatch.setattr(knowledge_service, "_get_qdrant_service", _get_qdrant_service_mock)

    return test_source, file_id, dummy_chunk_id


def _cleanup_test_environment(
    sql_local_service: SQLLocalService,
    mock_qdrant_service: MagicMock,
    test_source: SimpleNamespace,
) -> None:
    """Clean up test environment (drop table, schema, and mocked Qdrant collection)."""
    try:
        if sql_local_service.table_exists(test_source.database_table_name, test_source.database_schema):
            sql_local_service.drop_table(test_source.database_table_name, test_source.database_schema)
        with sql_local_service.engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {test_source.database_schema} CASCADE"))
            conn.commit()
    except Exception as e:
        LOGGER.warning(f"Failed to cleanup schema {test_source.database_schema}: {e}")

    # Cleanup mock Qdrant collection
    if mock_qdrant_service.collection_exists(test_source.qdrant_collection_name):
        mock_qdrant_service.delete_collection(test_source.qdrant_collection_name)


def test_chunk_operations_integration(
    monkeypatch: pytest.MonkeyPatch,
    sql_local_service: SQLLocalService,
    mock_qdrant_service: MagicMock,
    test_collection_name: str,
) -> None:
    """Test delete chunk operations with real SQL and mocked Qdrant operations."""
    test_source, file_id, dummy_chunk_id = _setup_test_environment(
        monkeypatch, sql_local_service, mock_qdrant_service, test_collection_name
    )

    mock_session = Mock()

    # ========== TEST DELETE CHUNK ==========
    initial_collection_data = mock_qdrant_service.get_collection_data(test_source.qdrant_collection_name)
    initial_chunk_ids = initial_collection_data["chunk_id"].tolist()
    initial_count = len(initial_chunk_ids)

    asyncio.run(
        knowledge_service.delete_chunk_service(
            session=mock_session,
            organization_id=uuid4(),
            source_id=test_source.id,
            chunk_id=dummy_chunk_id,
        )
    )

    final_collection_data = mock_qdrant_service.get_collection_data(test_source.qdrant_collection_name)
    if final_collection_data.empty:
        final_chunk_ids = []
    else:
        final_chunk_ids = final_collection_data["chunk_id"].tolist()
    assert dummy_chunk_id not in final_chunk_ids
    final_count = len(final_chunk_ids)
    assert final_count == initial_count - 1

    _cleanup_test_environment(sql_local_service, mock_qdrant_service, test_source)


def test_validate_qdrant_service_raises_when_collection_not_exists(
    monkeypatch: pytest.MonkeyPatch,
    mock_qdrant_service: MagicMock,
) -> None:
    """Test that non-existent Qdrant collection raises KnowledgeServiceQdrantConfigurationError."""
    mock_trace_manager = MockTraceManager(project_name="test")
    monkeypatch.setattr(knowledge_service, "get_trace_manager", lambda: mock_trace_manager)

    def _get_qdrant_service_mock(qdrant_schema, embedding_model_reference):
        return mock_qdrant_service

    monkeypatch.setattr(knowledge_service, "_get_qdrant_service", _get_qdrant_service_mock)

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

    with pytest.raises(KnowledgeServiceQdrantCollectionNotFoundError, match="does not exist"):
        asyncio.run(knowledge_service._validate_and_get_qdrant_service(source))


def test_validate_qdrant_service_raises_when_invalid_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that invalid qdrant_schema raises KnowledgeServiceQdrantConfigurationError."""
    mock_trace_manager = MockTraceManager(project_name="test")
    monkeypatch.setattr(knowledge_service, "get_trace_manager", lambda: mock_trace_manager)

    source = SimpleNamespace(
        id=uuid4(),
        database_schema="schema",
        database_table_name="table",
        qdrant_collection_name="test_collection",
        qdrant_schema={"invalid": "schema"},
        embedding_model_reference="openai:text-embedding-3-large",
    )

    with pytest.raises(KnowledgeServiceInvalidQdrantSchemaError, match="invalid qdrant_schema"):
        asyncio.run(knowledge_service._validate_and_get_qdrant_service(source))


def test_validate_qdrant_service_raises_when_invalid_embedding_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test invalid embedding_model_reference raises KnowledgeServiceQdrantConfigurationError."""
    mock_trace_manager = MockTraceManager(project_name="test")
    monkeypatch.setattr(knowledge_service, "get_trace_manager", lambda: mock_trace_manager)

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

    with pytest.raises(KnowledgeServiceInvalidEmbeddingModelReferenceError, match="invalid embedding_model_reference"):
        asyncio.run(knowledge_service._validate_and_get_qdrant_service(source))


def test_delete_chunk_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    sql_local_service: SQLLocalService,
    mock_qdrant_service: MagicMock,
    test_collection_name: str,
) -> None:
    """Test that deleting a chunk multiple times is idempotent."""
    test_source, file_id, dummy_chunk_id = _setup_test_environment(
        monkeypatch, sql_local_service, mock_qdrant_service, test_collection_name
    )

    mock_session = Mock()

    asyncio.run(
        knowledge_service.delete_chunk_service(
            session=mock_session,
            organization_id=uuid4(),
            source_id=test_source.id,
            chunk_id=dummy_chunk_id,
        )
    )

    asyncio.run(
        knowledge_service.delete_chunk_service(
            session=mock_session,
            organization_id=uuid4(),
            source_id=test_source.id,
            chunk_id=dummy_chunk_id,
        )
    )
    _cleanup_test_environment(sql_local_service, mock_qdrant_service, test_source)
