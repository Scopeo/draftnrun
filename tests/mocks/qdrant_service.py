"""Mock Qdrant service for testing."""

import asyncio
from typing import Iterator, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

from engine.qdrant_service import QdrantCollectionSchema, QdrantService


def mock_qdrant_service() -> Iterator[MagicMock]:
    """Create a mock Qdrant service with in-memory storage."""
    mock_qdrant = MagicMock(spec=QdrantService)

    collection_data: dict[str, list[dict]] = {}

    async def collection_exists_async(collection_name: str) -> bool:
        return collection_name in collection_data

    async def create_collection_async(collection_name: str, **kwargs) -> bool:
        if collection_name in collection_data:
            return False
        collection_data[collection_name] = []
        return True

    async def delete_collection_async(collection_name: str) -> bool:
        if collection_name in collection_data:
            del collection_data[collection_name]
            return True
        return False

    async def get_collection_data_rows_async(collection_name: str, **kwargs) -> list[dict]:
        if collection_name not in collection_data:
            raise ValueError(f"Collection '{collection_name}' does not exist")
        return [row.copy() for row in collection_data[collection_name]]

    async def _scroll_existing_ids_async(
        collection_name: str,
        id_field: str,
        timestamp_field: Optional[str] = None,
        filter: Optional[dict] = None,
        **kwargs,
    ) -> dict[str, Optional[str]]:
        if collection_name not in collection_data:
            raise ValueError(f"Collection '{collection_name}' does not exist")
        return {
            row[id_field]: row.get(timestamp_field) if timestamp_field else None
            for row in collection_data[collection_name]
            if id_field in row
        }

    async def add_chunks_async(list_chunks: list[dict], collection_name: str) -> bool:
        if collection_name not in collection_data:
            raise ValueError(f"Collection '{collection_name}' does not exist")
        collection_data[collection_name].extend(list_chunks)
        return True

    async def delete_chunks_async(
        point_ids: list[str], id_field: str, collection_name: str, filter: Optional[dict] = None
    ) -> bool:
        if collection_name not in collection_data:
            return True
        collection_data[collection_name] = [
            row for row in collection_data[collection_name] if row.get(id_field) not in point_ids
        ]
        return True

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

    async def sync_rows_with_collection_async(rows: list[dict], collection_name: str, **kwargs) -> bool:
        if collection_name not in collection_data:
            raise ValueError(f"Collection '{collection_name}' does not exist")
        collection_data[collection_name] = [row.copy() for row in rows]
        return True

    async def count_points_async(collection_name: str, **kwargs) -> int:
        if collection_name not in collection_data:
            raise ValueError(f"Collection '{collection_name}' does not exist")
        return len(collection_data[collection_name])

    mock_qdrant.collection_exists_async = AsyncMock(side_effect=collection_exists_async)
    mock_qdrant.create_collection_async = AsyncMock(side_effect=create_collection_async)
    mock_qdrant.delete_collection_async = AsyncMock(side_effect=delete_collection_async)
    mock_qdrant.get_collection_data_rows_async = AsyncMock(side_effect=get_collection_data_rows_async)
    mock_qdrant._scroll_existing_ids_async = AsyncMock(side_effect=_scroll_existing_ids_async)
    mock_qdrant.add_chunks_async = AsyncMock(side_effect=add_chunks_async)
    mock_qdrant.delete_chunks_async = AsyncMock(side_effect=delete_chunks_async)
    mock_qdrant._get_schema = Mock(side_effect=_get_schema)
    mock_qdrant.sync_rows_with_collection_async = AsyncMock(side_effect=sync_rows_with_collection_async)
    mock_qdrant.count_points_async = AsyncMock(side_effect=count_points_async)

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

    def sync_get_collection_data_rows(*args, **kwargs):
        collection_name = kwargs.get("collection_name") or (args[0] if args else None)
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "collection_name"}
        return asyncio.run(get_collection_data_rows_async(collection_name, **filtered_kwargs))

    def sync_add_chunks(*args, **kwargs):
        list_chunks = kwargs.get("list_chunks") or (args[0] if args else None)
        collection_name = kwargs.get("collection_name") or (args[1] if len(args) > 1 else None)
        return asyncio.run(add_chunks_async(list_chunks, collection_name))

    def sync_delete_chunks(*args, **kwargs):
        point_ids = kwargs.get("point_ids") or (args[0] if args else None)
        id_field = kwargs.get("id_field") or (args[1] if len(args) > 1 else None)
        collection_name = kwargs.get("collection_name") or (args[2] if len(args) > 2 else None)
        return asyncio.run(delete_chunks_async(point_ids, id_field, collection_name))

    def sync_sync_rows_with_collection(*args, **kwargs):
        rows = kwargs.get("rows") or (args[0] if args else None)
        collection_name = kwargs.get("collection_name") or (args[1] if len(args) > 1 else None)
        other_kwargs = {k: v for k, v in kwargs.items() if k not in ("rows", "collection_name")}
        return asyncio.run(sync_rows_with_collection_async(rows, collection_name, **other_kwargs))

    def sync_count_points(*args, **kwargs):
        collection_name = kwargs.get("collection_name") or (args[0] if args else None)
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "collection_name"}
        return asyncio.run(count_points_async(collection_name, **filtered_kwargs))

    mock_qdrant.collection_exists = Mock(side_effect=sync_collection_exists)
    mock_qdrant.create_collection = Mock(side_effect=sync_create_collection)
    mock_qdrant.delete_collection = Mock(side_effect=sync_delete_collection)
    mock_qdrant.get_collection_data_rows = Mock(side_effect=sync_get_collection_data_rows)
    mock_qdrant.add_chunks = Mock(side_effect=sync_add_chunks)
    mock_qdrant.delete_chunks = Mock(side_effect=sync_delete_chunks)
    mock_qdrant.sync_rows_with_collection = Mock(side_effect=sync_sync_rows_with_collection)
    mock_qdrant.count_points = Mock(side_effect=sync_count_points)

    mock_qdrant._collection_data = collection_data

    yield mock_qdrant

    collection_data.clear()
