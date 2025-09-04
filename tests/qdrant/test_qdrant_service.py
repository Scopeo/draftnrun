import pandas as pd
import asyncio
from uuid import uuid4

from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.llm_services.llm_service import EmbeddingService
from engine.agent.types import SourceChunk
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
    if asyncio.run(qdrant_agentic_service.collection_exists_async(TEST_COLLECTION_NAME)):
        asyncio.run(qdrant_agentic_service.delete_collection_async(TEST_COLLECTION_NAME))
    assert not asyncio.run(qdrant_agentic_service.collection_exists_async(TEST_COLLECTION_NAME))

    asyncio.run(qdrant_agentic_service.create_collection_async(collection_name=TEST_COLLECTION_NAME))
    assert asyncio.run(qdrant_agentic_service.collection_exists_async(TEST_COLLECTION_NAME))
    assert asyncio.run(qdrant_agentic_service.count_points_async(TEST_COLLECTION_NAME)) == 0
    asyncio.run(
        qdrant_agentic_service.add_chunks_async(
            list_chunks=chunks,
            collection_name=TEST_COLLECTION_NAME,
        )
    )
    assert asyncio.run(qdrant_agentic_service.count_points_async(TEST_COLLECTION_NAME)) == 2
    assert asyncio.run(
        qdrant_agentic_service.delete_chunks_async(
            point_ids=["1"],
            id_field="chunk_id",
            collection_name=TEST_COLLECTION_NAME,
        )
    )
    assert asyncio.run(qdrant_agentic_service.count_points_async(TEST_COLLECTION_NAME)) == 1
    retrieved_chunks = asyncio.run(
        qdrant_agentic_service.retrieve_similar_chunks_async(
            query_text="chunk2",
            collection_name=TEST_COLLECTION_NAME,
        )
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
    asyncio.run(qdrant_agentic_service.sync_df_with_collection_async(new_df_1, TEST_COLLECTION_NAME))
    assert asyncio.run(qdrant_agentic_service.count_points_async(TEST_COLLECTION_NAME)) == 2
    synced_df = asyncio.run(qdrant_agentic_service.get_collection_data_async(TEST_COLLECTION_NAME))
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
    asyncio.run(qdrant_agentic_service.sync_df_with_collection_async(new_df_2, TEST_COLLECTION_NAME))
    assert asyncio.run(qdrant_agentic_service.count_points_async(TEST_COLLECTION_NAME)) == 2
    synced_df = asyncio.run(qdrant_agentic_service.get_collection_data_async(TEST_COLLECTION_NAME))
    synced_df.sort_values(by="chunk_id", inplace=True)
    synced_df.reset_index(drop=True, inplace=True)
    assert synced_df.equals(new_df_2)

    assert asyncio.run(qdrant_agentic_service.delete_collection_async(TEST_COLLECTION_NAME))
    assert not asyncio.run(qdrant_agentic_service.collection_exists_async(TEST_COLLECTION_NAME))
