from unittest.mock import Mock

import pytest

from engine.agent.agent import SourceChunk
from engine.agent.rag.retriever import Retriever
from engine.qdrant_service import QdrantService
from tests.mocks.trace_manager import MockTraceManager

TEST_MAX_RETRIEVED_CHUNKS = 2


@pytest.fixture
def mock_trace_manager():
    return MockTraceManager(project_name="project_name")


@pytest.fixture
def mock_qdrant_service():
    return Mock(spec=QdrantService)


@pytest.fixture
def retriever(mock_trace_manager, mock_qdrant_service):
    return Retriever(
        trace_manager=mock_trace_manager,
        collection_name="test_collection",
        qdrant_service=mock_qdrant_service,
        max_retrieved_chunks=TEST_MAX_RETRIEVED_CHUNKS,
    )


def test_get_chunks_(retriever, mock_qdrant_service):
    mock_qdrant_service.retrieve_similar_chunks.return_value = [
        SourceChunk(content="chunk1", name="1", document_name="1", url="url1", metadata={"key": "value"}),
        SourceChunk(content="chunk2", name="2", document_name="2", url="url2", metadata={"key": "value"}),
    ]
    query_text = "test query"

    chunks = retriever.get_chunks(query_text=query_text)

    assert len(chunks) == 2
    assert chunks[0].content == "chunk1"
    assert chunks[1].content == "chunk2"
    mock_qdrant_service.retrieve_similar_chunks.assert_called_once_with(
        query_text=query_text,
        collection_name="test_collection",
        limit=TEST_MAX_RETRIEVED_CHUNKS,
        filter=None,
    )
