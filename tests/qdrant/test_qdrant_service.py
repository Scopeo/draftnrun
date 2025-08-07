import pandas as pd
import pytest
from typing import Union
from uuid import uuid4

from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.llm_services.llm_service import EmbeddingService
from engine.agent.types import SourceChunk
from engine.agent.utils import format_qdrant_filter
from tests.mocks.trace_manager import MockTraceManager

TEST_COLLECTION_NAME = f"test_agentic_ci_collection_{uuid4()}"


def test_qdrant_service():
    mock_trace_manager = MockTraceManager(project_name="test")
    embedding_service = EmbeddingService(
        trace_manager=mock_trace_manager,
        provider="openai",
        model_name="text-embedding-3-large",
    )

    qdrant_schema = QdrantCollectionSchema(
        chunk_id_field="chunk_id",
        content_field="content",
        file_id_field="file_id",
        url_id_field="url",
        last_edited_ts_field="last_edited_ts",
    )
    chunks = [
        {
            "chunk_id": "1",
            "content": "chunk1",
            "file_id": "file_id1",
            "url": "https//www.dummy1.com",
            "last_edited_ts": "2024-11-26 10:40:40",
        },
        {
            "chunk_id": "2",
            "content": "chunk2",
            "file_id": "file_id2",
            "url": "https//www.dummy2.com",
            "last_edited_ts": "2024-11-26 10:40:40",
        },
    ]
    qdrant_agentic_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=80.0,  # Increased timeout for tests
    )

    # Ensure a clean state
    if qdrant_agentic_service.collection_exists(TEST_COLLECTION_NAME):
        qdrant_agentic_service.delete_collection(TEST_COLLECTION_NAME)
    assert not qdrant_agentic_service.collection_exists(TEST_COLLECTION_NAME)

    qdrant_agentic_service.create_collection(collection_name=TEST_COLLECTION_NAME)
    assert qdrant_agentic_service.collection_exists(TEST_COLLECTION_NAME)
    assert qdrant_agentic_service.count_points(TEST_COLLECTION_NAME) == 0
    qdrant_agentic_service.add_chunks(
        list_chunks=chunks,
        collection_name=TEST_COLLECTION_NAME,
    )
    assert qdrant_agentic_service.count_points(TEST_COLLECTION_NAME) == 2
    assert qdrant_agentic_service.delete_chunks(
        point_ids=["1"],
        id_field="chunk_id",
        collection_name=TEST_COLLECTION_NAME,
    )
    assert qdrant_agentic_service.count_points(TEST_COLLECTION_NAME) == 1
    retrieved_chunks = qdrant_agentic_service.retrieve_similar_chunks(
        query_text="chunk2",
        collection_name=TEST_COLLECTION_NAME,
    )
    correct_chunk = SourceChunk(
        name="2",
        content="chunk2",
        document_name="file_id2",
        url="https//www.dummy2.com",
        metadata={},
    )
    assert retrieved_chunks[0] == correct_chunk

    new_df_1 = pd.DataFrame(
        [
            {
                "chunk_id": "1",
                "content": "chunk1",
                "file_id": "file_id1",
                "url": "https//www.dummy1.com",
                "last_edited_ts": "2025-01-2 10:40:40",
            },
            {
                "chunk_id": "2",
                "content": "chunk2",
                "url": "https//www.dummy2.com",
                "file_id": "file_id2",
                "last_edited_ts": "2025-01-2 10:40:40",
            },
        ]
    )
    qdrant_agentic_service.sync_df_with_collection(new_df_1, TEST_COLLECTION_NAME)
    assert qdrant_agentic_service.count_points(TEST_COLLECTION_NAME) == 2
    synced_df = qdrant_agentic_service.get_collection_data(TEST_COLLECTION_NAME)
    synced_df.sort_values(by="chunk_id", inplace=True)
    synced_df.reset_index(drop=True, inplace=True)
    assert synced_df.equals(new_df_1)

    new_df_2 = pd.DataFrame(
        [
            {
                "chunk_id": "1",
                "content": "chunk1",
                "file_id": "file_id1",
                "url": "https//www.dummy1.com",
                "last_edited_ts": "2025-01-2 10:40:40",
            },
            {
                "chunk_id": "3",
                "content": "chunk3",
                "file_id": "file_id3",
                "url": "https//www.dummy3.com",
                "last_edited_ts": "2025-01-2 10:40:40",
            },
        ]
    )
    qdrant_agentic_service.sync_df_with_collection(new_df_2, TEST_COLLECTION_NAME)
    assert qdrant_agentic_service.count_points(TEST_COLLECTION_NAME) == 2
    synced_df = qdrant_agentic_service.get_collection_data(TEST_COLLECTION_NAME)
    synced_df.sort_values(by="chunk_id", inplace=True)
    synced_df.reset_index(drop=True, inplace=True)
    assert synced_df.equals(new_df_2)

    assert qdrant_agentic_service.delete_collection(TEST_COLLECTION_NAME)
    assert not qdrant_agentic_service.collection_exists(TEST_COLLECTION_NAME)


@pytest.mark.parametrize(
    "filter_dict, filtering_condition, expected_chunk",
    [
        ({"metadata_1": ["a"]}, "OR", {"1"}),
        ({"metadata_2": ["cc"]}, "OR", {"2"}),
        ({"metadata_1": ["a"], "metadata_2": ["cc"]}, "OR", {"1", "2"}),
        ({"metadata_1": ["f", "g"]}, "OR", set()),
        ({"metadata_2": ["cc", "dd"]}, "OR", {"2"}),
        ({"metadata_1": ["a", "c"], "metadata_2": ["aa", "dd"]}, "AND", {"1", "2"}),
        ({"metadata_1": ["a"], "metadata_2": ["aa"]}, "AND", {"1"}),
    ],
)
def test_qdrant_filtering(
    filter_dict: dict[str, Union[list[str], str]], filtering_condition: str, expected_chunk: str
):
    """Tests the Qdrant filtering functionality using different filter conditions.

    Args:
        filter_dict (dict[str, Union[list[str], str]]): The filter dictionary to apply.
        filtering_condition (str): The filtering condition, either "AND" or "OR".
        expected_chunk (str): The expected chunk name to be retrieved.
    """
    mock_trace_manager = MockTraceManager(project_name="test")
    embedding_service = EmbeddingService(
        trace_manager=mock_trace_manager,
        provider="openai",
        model_name="text-embedding-3-large",
    )
    # Define the Qdrant schema
    qdrant_schema = QdrantCollectionSchema(
        chunk_id_field="chunk_id",
        content_field="content",
        file_id_field="file_id",
        url_id_field="url",
        last_edited_ts_field="last_edited_ts",
        metadata_fields_to_keep=["metadata_1", "metadata_2"],
    )

    # Define test data
    chunks = [
        {
            "chunk_id": "1",
            "content": "chunk1",
            "file_id": "file_id1",
            "url": "https//www.dummy1.com",
            "last_edited_ts": "2024-11-26 10:40:40",
            "metadata_1": ["a", "b"],
            "metadata_2": ["aa", "bb"],
        },
        {
            "chunk_id": "2",
            "content": "chunk2",
            "file_id": "file_id2",
            "url": "https//www.dummy2.com",
            "last_edited_ts": "2024-11-26 10:40:40",
            "metadata_1": ["c", "d"],
            "metadata_2": ["cc", "dd"],
        },
    ]

    # Initialize Qdrant service
    qdrant_agentic_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=80.0,  # Increased timeout for tests
    )

    # Ensure a clean state before testing
    if qdrant_agentic_service.collection_exists(TEST_COLLECTION_NAME):
        qdrant_agentic_service.delete_collection(TEST_COLLECTION_NAME)
    assert not qdrant_agentic_service.collection_exists(TEST_COLLECTION_NAME)

    # Create the collection and add chunks
    qdrant_agentic_service.create_collection(collection_name=TEST_COLLECTION_NAME)
    assert qdrant_agentic_service.collection_exists(TEST_COLLECTION_NAME)
    assert qdrant_agentic_service.count_points(TEST_COLLECTION_NAME) == 0

    qdrant_agentic_service.add_chunks(
        list_chunks=chunks,
        collection_name=TEST_COLLECTION_NAME,
    )
    assert qdrant_agentic_service.count_points(TEST_COLLECTION_NAME) == 2

    formatted_filter = format_qdrant_filter(filter_dict, filtering_condition)

    retrieved_chunks = qdrant_agentic_service.retrieve_similar_chunks(
        query_text="chunk1",
        collection_name=TEST_COLLECTION_NAME,
        filter=formatted_filter,
    )
    set_chunks = set([chunk.name for chunk in retrieved_chunks])
    assert expected_chunk == set_chunks
    assert qdrant_agentic_service.delete_collection(TEST_COLLECTION_NAME)
    assert not qdrant_agentic_service.collection_exists(TEST_COLLECTION_NAME)
