"""Mock Qdrant service for testing."""

import asyncio
from typing import Iterator, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

import pandas as pd

from engine.qdrant_service import QdrantCollectionSchema, QdrantService


def mock_qdrant_service() -> Iterator[MagicMock]:
    """Create a mock Qdrant service with in-memory storage."""
    mock_qdrant = MagicMock(spec=QdrantService)

    # Mock collection data storage (in-memory)
    collection_data: dict[str, pd.DataFrame] = {}

    # Mock collection_exists_async
    async def collection_exists_async(collection_name: str) -> bool:
        return collection_name in collection_data

    # Mock create_collection_async
    async def create_collection_async(collection_name: str, **kwargs) -> bool:
        if collection_name in collection_data:
            return False
        collection_data[collection_name] = pd.DataFrame()
        return True

    # Mock delete_collection_async
    async def delete_collection_async(collection_name: str) -> bool:
        if collection_name in collection_data:
            del collection_data[collection_name]
            return True
        return False

    # Mock get_collection_data_async
    async def get_collection_data_async(collection_name: str, **kwargs) -> pd.DataFrame:
        if collection_name not in collection_data:
            return pd.DataFrame()
        return collection_data[collection_name].copy()

    # Mock add_chunks_async
    async def add_chunks_async(list_chunks: list[dict], collection_name: str) -> bool:
        if collection_name not in collection_data:
            collection_data[collection_name] = pd.DataFrame()

        new_df = pd.DataFrame(list_chunks)
        if collection_data[collection_name].empty:
            collection_data[collection_name] = new_df
        else:
            collection_data[collection_name] = pd.concat([collection_data[collection_name], new_df], ignore_index=True)
        return True

    # Mock delete_chunks_async
    async def delete_chunks_async(
        point_ids: list[str], id_field: str, collection_name: str, filter: Optional[dict] = None
    ) -> bool:
        if collection_name not in collection_data:
            return True
        if collection_data[collection_name].empty:
            return True

        df = collection_data[collection_name]
        collection_data[collection_name] = df[~df[id_field].isin(point_ids)]
        return True

    # Mock _get_schema
    def _get_schema(collection_name: str) -> QdrantCollectionSchema:
        return QdrantCollectionSchema(
            chunk_id_field="chunk_id",
            content_field="content",
            file_id_field="file_id",
            url_id_field="url",
            last_edited_ts_field="last_edited_ts",
            source_id_field="source_id",
            metadata_fields_to_keep={"metadata_to_keep_by_qdrant_field"},
        )

    # Mock sync_df_with_collection_async
    async def sync_df_with_collection_async(df: pd.DataFrame, collection_name: str, **kwargs) -> bool:
        collection_data[collection_name] = df.copy()
        return True

    # Set up async methods
    mock_qdrant.collection_exists_async = AsyncMock(side_effect=collection_exists_async)
    mock_qdrant.create_collection_async = AsyncMock(side_effect=create_collection_async)
    mock_qdrant.delete_collection_async = AsyncMock(side_effect=delete_collection_async)
    mock_qdrant.get_collection_data_async = AsyncMock(side_effect=get_collection_data_async)
    mock_qdrant.add_chunks_async = AsyncMock(side_effect=add_chunks_async)
    mock_qdrant.delete_chunks_async = AsyncMock(side_effect=delete_chunks_async)
    mock_qdrant._get_schema = Mock(side_effect=_get_schema)
    mock_qdrant.sync_df_with_collection_async = AsyncMock(side_effect=sync_df_with_collection_async)

    def sync_collection_exists(*args, **kwargs):
        collection_name = kwargs.get("collection_name") or (args[0] if args else None)
        return asyncio.run(collection_exists_async(collection_name))

    def sync_create_collection(*args, **kwargs):
        collection_name = kwargs.get("collection_name") or (args[0] if args else None)
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "collection_name"}
        return asyncio.run(create_collection_async(collection_name, **filtered_kwargs))

    def sync_delete_collection(*args, **kwargs):
        collection_name = kwargs.get("collection_name") or (args[0] if args else None)
        return asyncio.run(delete_collection_async(collection_name))

    def sync_get_collection_data(*args, **kwargs):
        collection_name = kwargs.get("collection_name") or (args[0] if args else None)
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "collection_name"}
        return asyncio.run(get_collection_data_async(collection_name, **filtered_kwargs))

    def sync_add_chunks(*args, **kwargs):
        list_chunks = kwargs.get("list_chunks") or (args[0] if args else None)
        collection_name = kwargs.get("collection_name") or (args[1] if len(args) > 1 else None)
        return asyncio.run(add_chunks_async(list_chunks, collection_name))

    def sync_delete_chunks(*args, **kwargs):
        point_ids = kwargs.get("point_ids") or (args[0] if args else None)
        id_field = kwargs.get("id_field") or (args[1] if len(args) > 1 else None)
        collection_name = kwargs.get("collection_name") or (args[2] if len(args) > 2 else None)
        return asyncio.run(delete_chunks_async(point_ids, id_field, collection_name))

    def sync_sync_df_with_collection(*args, **kwargs):
        df = kwargs.get("df") or (args[0] if args else None)
        collection_name = kwargs.get("collection_name") or (args[1] if len(args) > 1 else None)
        other_kwargs = {k: v for k, v in kwargs.items() if k not in ("df", "collection_name")}
        return asyncio.run(sync_df_with_collection_async(df, collection_name, **other_kwargs))

    mock_qdrant.collection_exists = Mock(side_effect=sync_collection_exists)
    mock_qdrant.create_collection = Mock(side_effect=sync_create_collection)
    mock_qdrant.delete_collection = Mock(side_effect=sync_delete_collection)
    mock_qdrant.get_collection_data = Mock(side_effect=sync_get_collection_data)
    mock_qdrant.add_chunks = Mock(side_effect=sync_add_chunks)
    mock_qdrant.delete_chunks = Mock(side_effect=sync_delete_chunks)
    mock_qdrant.sync_df_with_collection = Mock(side_effect=sync_sync_df_with_collection)

    # Store collection_data for cleanup
    mock_qdrant._collection_data = collection_data

    yield mock_qdrant

    # Cleanup
    collection_data.clear()
