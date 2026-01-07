from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pandas as pd

from engine.components.types import SourceChunk
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import FieldSchema, QdrantCollectionSchema, QdrantService
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
        timeout=60.0,  # Increased timeout for tests
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

    new_df_1 = pd.DataFrame([
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
    ])
    qdrant_agentic_service.sync_df_with_collection(new_df_1, TEST_COLLECTION_NAME)
    assert qdrant_agentic_service.count_points(TEST_COLLECTION_NAME) == 2
    synced_df = qdrant_agentic_service.get_collection_data(TEST_COLLECTION_NAME)
    synced_df.sort_values(by="chunk_id", inplace=True)
    synced_df.reset_index(drop=True, inplace=True)
    assert synced_df.equals(new_df_1)

    new_df_2 = pd.DataFrame([
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
    ])
    qdrant_agentic_service.sync_df_with_collection(new_df_2, TEST_COLLECTION_NAME)
    assert qdrant_agentic_service.count_points(TEST_COLLECTION_NAME) == 2
    synced_df = qdrant_agentic_service.get_collection_data(TEST_COLLECTION_NAME)
    synced_df.sort_values(by="chunk_id", inplace=True)
    synced_df.reset_index(drop=True, inplace=True)
    assert synced_df.equals(new_df_2)

    assert qdrant_agentic_service.delete_collection(TEST_COLLECTION_NAME)
    assert not qdrant_agentic_service.collection_exists(TEST_COLLECTION_NAME)


def test_multiple_metadata_fields_index_creation():
    """
    Test that verifies the bug fix for DRA-575.
    Ensures that index creation is called for ALL metadata fields, not just the last one.
    """
    TEST_COLLECTION_NAME_MULTI = f"test_multi_metadata_{uuid4()}"

    mock_trace_manager = MockTraceManager(project_name="test")
    embedding_service = EmbeddingService(
        trace_manager=mock_trace_manager,
        provider="openai",
        model_name="text-embedding-3-large",
    )

    # Create schema with multiple metadata fields and types
    qdrant_schema = QdrantCollectionSchema(
        chunk_id_field="chunk_id",
        content_field="content",
        file_id_field="file_id",
        url_id_field="url",
        last_edited_ts_field="last_edited_ts",
        metadata_fields_to_keep={"author", "status", "priority", "version"},
        metadata_field_types={
            "author": "VARCHAR",
            "status": "VARCHAR",
            "priority": "INTEGER",
            "version": "FLOAT",
        },
    )

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    # Create collection
    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_MULTI):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_MULTI)

    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_MULTI)

    # Add a chunk so collection has data
    chunks = [
        {
            "chunk_id": "1",
            "content": "test content",
            "file_id": "file_1",
            "url": "https://test.com",
            "last_edited_ts": "2024-11-26 10:40:40",
            "author": "John Doe",
            "status": "draft",
            "priority": 1,
            "version": 1.0,
        }
    ]
    qdrant_service.add_chunks(list_chunks=chunks, collection_name=TEST_COLLECTION_NAME_MULTI)

    # Mock create_index_if_needed_async to track calls
    original_create_index = qdrant_service.create_index_if_needed_async
    call_tracker = []

    async def mock_create_index(collection_name: str, field_name: str, field_schema_type: FieldSchema):
        call_tracker.append({
            "collection_name": collection_name,
            "field_name": field_name,
            "field_schema_type": field_schema_type,
        })
        # Call the original method to maintain functionality
        return await original_create_index(collection_name, field_name, field_schema_type)

    # Patch the method
    qdrant_service.create_index_if_needed_async = mock_create_index

    # Call get_collection_data which triggers index creation
    qdrant_service.get_collection_data(TEST_COLLECTION_NAME_MULTI)

    # Verify that create_index_if_needed_async was called for ALL metadata fields
    metadata_field_calls = [
        call for call in call_tracker if call["field_name"] in qdrant_schema.metadata_fields_to_keep
    ]

    # Should have 4 calls, one for each metadata field
    assert len(metadata_field_calls) == 4, (
        f"Expected 4 index creation calls for metadata fields, got {len(metadata_field_calls)}"
    )

    # Verify each field was called with the correct type
    field_type_map = {
        "author": FieldSchema.KEYWORD,
        "status": FieldSchema.KEYWORD,
        "priority": FieldSchema.INTEGER,
        "version": FieldSchema.FLOAT,
    }

    for field_name, expected_type in field_type_map.items():
        matching_calls = [call for call in metadata_field_calls if call["field_name"] == field_name]
        assert len(matching_calls) == 1, f"Expected exactly 1 call for field '{field_name}', got {len(matching_calls)}"
        assert matching_calls[0]["field_schema_type"] == expected_type, (
            f"Field '{field_name}' should have type {expected_type}, got {matching_calls[0]['field_schema_type']}"
        )

    # Also verify chunk_id and last_edited_ts indexes were created
    chunk_id_calls = [call for call in call_tracker if call["field_name"] == "chunk_id"]
    assert len(chunk_id_calls) >= 1, "chunk_id index should be created"

    last_edited_calls = [call for call in call_tracker if call["field_name"] == "last_edited_ts"]
    assert len(last_edited_calls) >= 1, "last_edited_ts index should be created"

    # Cleanup
    qdrant_service.delete_collection(TEST_COLLECTION_NAME_MULTI)


def test_custom_embedding_size_collection_creation():
    """
    Test that verifies Qdrant collections are created with the correct embedding size
    from the embedding service, especially for custom/local models with different dimensions.
    """
    TEST_COLLECTION_NAME_CUSTOM = f"test_custom_embedding_{uuid4()}"
    CUSTOM_EMBEDDING_SIZE = 1536

    mock_embedding_service = MagicMock()
    mock_embedding_service.embedding_size = CUSTOM_EMBEDDING_SIZE

    fake_embeddings = [[0.1] * CUSTOM_EMBEDDING_SIZE, [0.2] * CUSTOM_EMBEDDING_SIZE]
    mock_embedding_data = [MagicMock(embedding=emb) for emb in fake_embeddings]
    mock_embedding_service.embed_text_async = AsyncMock(return_value=mock_embedding_data)

    qdrant_schema = QdrantCollectionSchema(
        chunk_id_field="chunk_id",
        content_field="content",
        file_id_field="file_id",
        url_id_field="url",
    )

    qdrant_service = QdrantService.from_defaults(
        embedding_service=mock_embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_CUSTOM):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_CUSTOM)

    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_CUSTOM)

    assert qdrant_service.collection_exists(TEST_COLLECTION_NAME_CUSTOM)

    chunks = [
        {
            "chunk_id": "1",
            "content": "test content 1",
            "file_id": "file_1",
            "url": "https://test1.com",
        },
        {
            "chunk_id": "2",
            "content": "test content 2",
            "file_id": "file_2",
            "url": "https://test2.com",
        },
    ]

    result = qdrant_service.add_chunks(
        list_chunks=chunks,
        collection_name=TEST_COLLECTION_NAME_CUSTOM,
    )

    assert result is True
    assert qdrant_service.count_points(TEST_COLLECTION_NAME_CUSTOM) == 2

    mock_embedding_service.embed_text_async.assert_called_with(["test content 1", "test content 2"])

    qdrant_service.delete_collection(TEST_COLLECTION_NAME_CUSTOM)


def test_merge_qdrant_filters():
    TEST_COLLECTION_NAME_MERGE = f"test_merge_filters_{uuid4()}"

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
        metadata_fields_to_keep={"field_1", "field_2"},
        metadata_field_types={
            "field_1": "VARCHAR",
            "field_2": "VARCHAR",
        },
    )

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_MERGE):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_MERGE)

    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_MERGE)

    chunks = [
        {
            "chunk_id": "1",
            "content": "chunk1",
            "file_id": "file_1",
            "url": "https://test1.com",
            "field_1": "value_1",
            "field_2": None,
        },
        {
            "chunk_id": "2",
            "content": "chunk2",
            "file_id": "file_2",
            "url": "https://test2.com",
            "field_1": "value_1",
            "field_2": None,
        },
        {
            "chunk_id": "3",
            "content": "chunk3",
            "file_id": "file_3",
            "url": "https://test3.com",
            "field_1": None,
            "field_2": "value_2",
        },
        {
            "chunk_id": "4",
            "content": "chunk4",
            "file_id": "file_4",
            "url": "https://test4.com",
            "field_1": None,
            "field_2": "value_2",
        },
        {
            "chunk_id": "5",
            "content": "chunk5",
            "file_id": "file_5",
            "url": "https://test5.com",
            "field_1": "value_1",
            "field_2": "value_2",
        },
    ]

    qdrant_service.add_chunks(list_chunks=chunks, collection_name=TEST_COLLECTION_NAME_MERGE)

    from engine.components.utils import merge_qdrant_filters_with_and_conditions

    filter_1 = {"must": [{"key": "field_1", "match": {"value": "value_1"}}]}
    filter_2 = {"must": [{"key": "field_2", "match": {"value": "value_2"}}]}

    results_filter_1 = qdrant_service.retrieve_similar_chunks(
        query_text="chunk",
        collection_name=TEST_COLLECTION_NAME_MERGE,
        filter=filter_1,
        limit=10,
    )
    assert len(results_filter_1) == 3
    assert set(chunk.name for chunk in results_filter_1) == {"1", "2", "5"}

    results_filter_2 = qdrant_service.retrieve_similar_chunks(
        query_text="chunk",
        collection_name=TEST_COLLECTION_NAME_MERGE,
        filter=filter_2,
        limit=10,
    )
    assert len(results_filter_2) == 3
    assert set(chunk.name for chunk in results_filter_2) == {"3", "4", "5"}

    merged_filter = merge_qdrant_filters_with_and_conditions(filter_1, filter_2)
    results_merged = qdrant_service.retrieve_similar_chunks(
        query_text="chunk",
        collection_name=TEST_COLLECTION_NAME_MERGE,
        filter=merged_filter,
        limit=10,
    )
    assert len(results_merged) == 1
    assert results_merged[0].name == "5"

    qdrant_service.delete_collection(TEST_COLLECTION_NAME_MERGE)


def test_search_vectors():
    """Test search_vectors method."""
    TEST_COLLECTION_NAME_SEARCH = f"test_search_vectors_{uuid4()}"

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
    )

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_SEARCH):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_SEARCH)

    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_SEARCH)

    chunks = [
        {
            "chunk_id": "1",
            "content": "test content 1",
            "file_id": "file_1",
            "url": "https://test1.com",
        },
        {
            "chunk_id": "2",
            "content": "test content 2",
            "file_id": "file_2",
            "url": "https://test2.com",
        },
    ]

    qdrant_service.add_chunks(list_chunks=chunks, collection_name=TEST_COLLECTION_NAME_SEARCH)

    # Create a query vector (using embedding service)
    query_vector = qdrant_service._build_vectors("test content 1")[0]

    # Search without filter
    results = qdrant_service.search_vectors(
        query_vector=query_vector,
        collection_name=TEST_COLLECTION_NAME_SEARCH,
        limit=10,
    )

    assert len(results) >= 1
    assert isinstance(results[0], tuple)
    assert len(results[0]) == 3  # (id, score, payload)

    # Search with filter
    filter_dict = {"must": [{"key": "chunk_id", "match": {"value": "1"}}]}
    filtered_results = qdrant_service.search_vectors(
        query_vector=query_vector,
        collection_name=TEST_COLLECTION_NAME_SEARCH,
        filter=filter_dict,
        limit=10,
    )

    assert len(filtered_results) >= 1
    assert filtered_results[0][0] == qdrant_service.get_uuid("1")

    qdrant_service.delete_collection(TEST_COLLECTION_NAME_SEARCH)


def test_get_chunk_data_by_id():
    """Test get_chunk_data_by_id method."""
    TEST_COLLECTION_NAME_GET = f"test_get_chunk_data_{uuid4()}"

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
    )

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_GET):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_GET)

    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_GET)

    chunks = [
        {
            "chunk_id": "1",
            "content": "test content 1",
            "file_id": "file_1",
            "url": "https://test1.com",
        },
        {
            "chunk_id": "2",
            "content": "test content 2",
            "file_id": "file_2",
            "url": "https://test2.com",
        },
    ]

    qdrant_service.add_chunks(list_chunks=chunks, collection_name=TEST_COLLECTION_NAME_GET)

    # Get chunk data by IDs
    chunk_1_uuid = qdrant_service.get_uuid("1")
    chunk_2_uuid = qdrant_service.get_uuid("2")

    results = qdrant_service.get_chunk_data_by_id(
        vector_ids=[chunk_1_uuid, chunk_2_uuid],
        collection_name=TEST_COLLECTION_NAME_GET,
    )

    assert len(results) == 2
    assert any(result.get("payload", {}).get("chunk_id") == "1" for result in results)
    assert any(result.get("payload", {}).get("chunk_id") == "2" for result in results)

    # Test with single ID
    single_result = qdrant_service.get_chunk_data_by_id(
        vector_ids=[chunk_1_uuid],
        collection_name=TEST_COLLECTION_NAME_GET,
    )

    assert len(single_result) == 1
    assert single_result[0].get("payload", {}).get("chunk_id") == "1"

    qdrant_service.delete_collection(TEST_COLLECTION_NAME_GET)


def test_get_points():
    """Test get_points method."""
    TEST_COLLECTION_NAME_POINTS = f"test_get_points_{uuid4()}"

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
    )

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_POINTS):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_POINTS)

    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_POINTS)

    chunks = [
        {
            "chunk_id": "1",
            "content": "test content 1",
            "file_id": "file_1",
            "url": "https://test1.com",
        },
        {
            "chunk_id": "2",
            "content": "test content 2",
            "file_id": "file_2",
            "url": "https://test2.com",
        },
    ]

    qdrant_service.add_chunks(list_chunks=chunks, collection_name=TEST_COLLECTION_NAME_POINTS)

    # Get all points
    all_points = qdrant_service.get_points(
        collection_name=TEST_COLLECTION_NAME_POINTS,
    )

    assert len(all_points) == 2

    # Get points with filter
    filter_dict = {"must": [{"key": "chunk_id", "match": {"value": "1"}}]}
    filtered_points = qdrant_service.get_points(
        collection_name=TEST_COLLECTION_NAME_POINTS,
        filter=filter_dict,
    )

    assert len(filtered_points) == 1
    assert filtered_points[0].get("payload", {}).get("chunk_id") == "1"

    qdrant_service.delete_collection(TEST_COLLECTION_NAME_POINTS)


def test_delete_points():
    """Test delete_points method."""
    TEST_COLLECTION_NAME_DELETE = f"test_delete_points_{uuid4()}"

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
    )

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_DELETE):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_DELETE)

    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_DELETE)

    chunks = [
        {
            "chunk_id": "1",
            "content": "test content 1",
            "file_id": "file_1",
            "url": "https://test1.com",
        },
        {
            "chunk_id": "2",
            "content": "test content 2",
            "file_id": "file_2",
            "url": "https://test2.com",
        },
    ]

    qdrant_service.add_chunks(list_chunks=chunks, collection_name=TEST_COLLECTION_NAME_DELETE)

    assert qdrant_service.count_points(TEST_COLLECTION_NAME_DELETE) == 2

    # Get point IDs
    points = qdrant_service.get_points(collection_name=TEST_COLLECTION_NAME_DELETE)
    point_ids = [point["id"] for point in points]

    # Delete one point
    result = qdrant_service.delete_points(
        point_ids=[point_ids[0]],
        collection_name=TEST_COLLECTION_NAME_DELETE,
    )

    assert result is True
    assert qdrant_service.count_points(TEST_COLLECTION_NAME_DELETE) == 1

    qdrant_service.delete_collection(TEST_COLLECTION_NAME_DELETE)


def test_insert_points_in_collection():
    """Test insert_points_in_collection method."""
    TEST_COLLECTION_NAME_INSERT = f"test_insert_points_{uuid4()}"

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
    )

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_INSERT):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_INSERT)

    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_INSERT)

    # Create points manually
    vector_1 = qdrant_service._build_vectors("test content 1")[0]
    vector_2 = qdrant_service._build_vectors("test content 2")[0]

    points = [
        {
            "id": qdrant_service.get_uuid("1"),
            "payload": {
                "chunk_id": "1",
                "content": "test content 1",
                "file_id": "file_1",
                "url": "https://test1.com",
            },
            "vector": vector_1,
        },
        {
            "id": qdrant_service.get_uuid("2"),
            "payload": {
                "chunk_id": "2",
                "content": "test content 2",
                "file_id": "file_2",
                "url": "https://test2.com",
            },
            "vector": vector_2,
        },
    ]

    result = qdrant_service.insert_points_in_collection(
        points=points,
        collection_name=TEST_COLLECTION_NAME_INSERT,
    )

    assert result is True
    assert qdrant_service.count_points(TEST_COLLECTION_NAME_INSERT) == 2

    qdrant_service.delete_collection(TEST_COLLECTION_NAME_INSERT)


def test_list_collection_names():
    """Test list_collection_names method."""
    TEST_COLLECTION_NAME_LIST_1 = f"test_list_1_{uuid4()}"
    TEST_COLLECTION_NAME_LIST_2 = f"test_list_2_{uuid4()}"

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
    )

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    # Cleanup if exists
    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_LIST_1):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_LIST_1)
    if qdrant_service.collection_exists(TEST_COLLECTION_NAME_LIST_2):
        qdrant_service.delete_collection(TEST_COLLECTION_NAME_LIST_2)

    # Create collections
    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_LIST_1)
    qdrant_service.create_collection(collection_name=TEST_COLLECTION_NAME_LIST_2)

    # List collections
    collection_names = qdrant_service.list_collection_names()

    assert TEST_COLLECTION_NAME_LIST_1 in collection_names
    assert TEST_COLLECTION_NAME_LIST_2 in collection_names

    # Cleanup
    qdrant_service.delete_collection(TEST_COLLECTION_NAME_LIST_1)
    qdrant_service.delete_collection(TEST_COLLECTION_NAME_LIST_2)


def test_apply_date_penalty_to_chunks():
    """Test apply_date_penalty_to_chunks method."""
    from datetime import datetime

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

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
        timeout=60.0,
    )

    # Create mock vector results with different dates
    current_year = datetime.today().year
    old_date = f"{current_year - 2}-01-01T00:00:00"
    recent_date = f"{current_year}-01-01T00:00:00"

    vector_results = [
        ("id1", 0.9, {"last_edited_ts": old_date, "chunk_id": "1"}),
        ("id2", 0.8, {"last_edited_ts": recent_date, "chunk_id": "2"}),
        ("id3", 0.7, {"last_edited_ts": None, "chunk_id": "3"}),
    ]

    # Apply penalty
    vector_ids, scores, payloads = qdrant_service.apply_date_penalty_to_chunks(
        vector_results=vector_results,
        metadata_date_key=["last_edited_ts"],
        default_penalty_rate=0.1,
        chunk_age_penalty_rate=0.05,
        max_retrieved_chunks_after_penalty=3,
    )

    assert len(vector_ids) == 3
    assert len(scores) == 3
    assert len(payloads) == 3

    # After penalty, scores should be sorted in descending order
    assert scores[0] >= scores[1] >= scores[2]

    # Chunk without date should have default penalty
    no_date_idx = list(vector_ids).index("id3")
    assert scores[no_date_idx] == 0.1
