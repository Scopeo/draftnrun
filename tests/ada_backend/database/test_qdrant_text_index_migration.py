import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from engine.qdrant_service import FieldSchema

MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "ada_backend/database/alembic/versions/b8c9d0e1f2a3_update_db_source_text_qdrant_indexes.py"
)
spec = importlib.util.spec_from_file_location("qdrant_text_index_migration", MIGRATION_PATH)
migration = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(migration)


def test_metadata_fields_for_text_indexes_uses_schema_types_and_skips_identifiers():
    qdrant_schema = {
        "metadata_fields_to_keep": ["author", "content", "source_id", "published_at", "priority", "external_uuid"],
        "metadata_field_types": {
            "author": "VARCHAR",
            "content": "VARCHAR",
            "source_id": "VARCHAR",
            "published_at": "DATETIME",
            "priority": "INTEGER",
            "external_uuid": "VARCHAR",
        },
    }

    assert migration._metadata_fields_for_text_indexes(qdrant_schema) == ["author"]


@pytest.mark.asyncio
async def test_update_collection_indexes_recreates_only_requested_fields():
    qdrant_service = AsyncMock()
    qdrant_service.collection_exists_async.return_value = True

    await migration._update_collection_indexes(
        qdrant_service=qdrant_service,
        collection_name="collection",
        field_names=["author"],
        target_schema=FieldSchema.TEXT,
    )

    qdrant_service.create_index_if_needed_async.assert_called_once_with(
        collection_name="collection",
        field_name="author",
        field_schema_type=FieldSchema.TEXT,
    )


@pytest.mark.asyncio
async def test_update_collection_indexes_skips_missing_collection():
    qdrant_service = AsyncMock()
    qdrant_service.collection_exists_async.return_value = False

    await migration._update_collection_indexes(
        qdrant_service=qdrant_service,
        collection_name="missing_collection",
        field_names=["author"],
        target_schema=FieldSchema.TEXT,
    )

    qdrant_service.create_index_if_needed_async.assert_not_called()
