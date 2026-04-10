from unittest.mock import AsyncMock, Mock

import pytest

from engine.components.rag.retriever import Retriever, RetrieverInputs
from engine.components.types import SourceChunk
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import QdrantService
from tests.mocks.trace_manager import MockTraceManager

TEST_MAX_RETRIEVED_CHUNKS = 2


@pytest.fixture
def mock_trace_manager():
    return MockTraceManager(project_name="project_name")


@pytest.fixture
def mock_qdrant_service():
    mock_qdrant_service = Mock(spec=QdrantService)
    mock_embedding_service = Mock(spec=EmbeddingService)
    mock_embedding_service._model_name = "test_model"
    mock_qdrant_service._embedding_service = mock_embedding_service
    # Set up the async method with proper AsyncMock
    mock_qdrant_service.retrieve_similar_chunks_async = AsyncMock()
    return mock_qdrant_service


@pytest.fixture
def retriever(mock_trace_manager, mock_qdrant_service):
    return Retriever(
        trace_manager=mock_trace_manager,
        collection_name="test_collection",
        qdrant_service=mock_qdrant_service,
        max_retrieved_chunks=TEST_MAX_RETRIEVED_CHUNKS,
    )


@pytest.mark.asyncio
async def test_get_chunks_(retriever, mock_qdrant_service):
    mock_qdrant_service.retrieve_similar_chunks_async.return_value = [
        SourceChunk(content="chunk1", name="1", document_name="1", url="url1", metadata={"key": "value"}),
        SourceChunk(content="chunk2", name="2", document_name="2", url="url2", metadata={"key": "value"}),
    ]
    query_text = "test query"

    chunks = await retriever.get_chunks(query_text=query_text)

    assert len(chunks) == 2
    assert chunks[0].content == "chunk1"
    assert chunks[1].content == "chunk2"
    mock_qdrant_service.retrieve_similar_chunks_async.assert_called_once_with(
        query_text=query_text,
        collection_name="test_collection",
        limit=TEST_MAX_RETRIEVED_CHUNKS,
        filter=None,
        enable_date_penalty_for_chunks=False,
        chunk_age_penalty_rate=None,
        default_penalty_rate=None,
        metadata_date_key=[],
        max_retrieved_chunks_after_penalty=None,
        source_schemas=None,
    )


@pytest.mark.asyncio
async def test_run_with_string_filters(retriever, mock_qdrant_service):
    """Regression: LLM or LiteralNode may pass filters as JSON string '{}' instead of dict."""
    mock_qdrant_service.retrieve_similar_chunks_async.return_value = [
        SourceChunk(content="chunk1", name="1", document_name="1", url="url1", metadata={"key": "value"}),
    ]

    result = await retriever.run(query="test query", filters="{}")

    assert result.messages
    mock_qdrant_service.retrieve_similar_chunks_async.assert_called_once()
    call_kwargs = mock_qdrant_service.retrieve_similar_chunks_async.call_args.kwargs
    assert call_kwargs["filter"] is None or isinstance(call_kwargs["filter"], dict)


def test_retriever_inputs_accepts_string_filters_after_preprocessing():
    """Regression: RetrieverInputs should accept dict filters after component preprocessing."""
    from engine.components.component import _coerce_inputs_for_model

    data = {"query": "test", "filters": "{}"}
    _coerce_inputs_for_model(data, RetrieverInputs)
    inputs = RetrieverInputs(**data)
    assert inputs.filters == {}

    data2 = {"query": "test", "filters": '{"must": [{"key": "date", "range": {"gte": "2024-01-01"}}]}'}
    _coerce_inputs_for_model(data2, RetrieverInputs)
    inputs2 = RetrieverInputs(**data2)
    assert inputs2.filters == {"must": [{"key": "date", "range": {"gte": "2024-01-01"}}]}
