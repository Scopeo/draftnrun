"""update_db_source_text_qdrant_indexes

Revision ID: b8c9d0e1f2a3
Revises: a3b4c5d6e7f9
Create Date: 2026-05-07

Recreate eligible database-source Qdrant metadata indexes as full-text indexes.
Downgrade restores those eligible fields to keyword indexes, but cannot preserve
the text-index matching behavior introduced by this migration.
"""

import asyncio
import logging
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from engine.qdrant_service import (
    FieldSchema,
    QdrantService,
    map_metadata_field_to_qdrant_field_schema,
    should_create_payload_index,
)

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a3b4c5d6e7f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"

LOGGER = logging.getLogger("alembic.migration")


def _metadata_fields_for_text_indexes(qdrant_schema: dict) -> list[str]:
    metadata_fields = qdrant_schema.get("metadata_fields_to_keep") or []
    metadata_field_types = qdrant_schema.get("metadata_field_types") or {}
    fields_to_update = []

    for field_name in metadata_fields:
        if not should_create_payload_index(field_name):
            continue

        internal_type = metadata_field_types.get(field_name)
        if not internal_type:
            continue
        if map_metadata_field_to_qdrant_field_schema(field_name, internal_type) == FieldSchema.TEXT:
            fields_to_update.append(field_name)

    return fields_to_update


async def _update_collection_indexes(
    qdrant_service: QdrantService,
    collection_name: str,
    field_names: list[str],
    target_schema: FieldSchema,
) -> None:
    if not await qdrant_service.collection_exists_async(collection_name):
        LOGGER.info("Qdrant collection %s does not exist. Skipping.", collection_name)
        return

    for field_name in field_names:
        LOGGER.info(
            "Ensuring Qdrant index for database source collection=%s field=%s target=%s",
            collection_name,
            field_name,
            target_schema.value,
        )
        await qdrant_service.create_index_if_needed_async(
            collection_name=collection_name,
            field_name=field_name,
            field_schema_type=target_schema,
        )


async def _migrate_indexes(target_schema: FieldSchema) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        text(
            """
            SELECT id, qdrant_collection_name, qdrant_schema
            FROM data_sources
            WHERE type = 'database'
              AND qdrant_collection_name IS NOT NULL
              AND qdrant_schema IS NOT NULL
            """
        )
    ).fetchall()

    if not rows:
        LOGGER.info("No database sources with Qdrant schemas found. Nothing to migrate.")
        return

    qdrant_service = QdrantService.from_defaults()
    for source_id, collection_name, qdrant_schema in rows:
        fields_to_update = _metadata_fields_for_text_indexes(qdrant_schema)
        if not fields_to_update:
            LOGGER.info("No text metadata fields to update for database source %s.", source_id)
            continue

        LOGGER.info(
            "Updating %s Qdrant metadata indexes for database source %s in collection %s.",
            len(fields_to_update),
            source_id,
            collection_name,
        )
        await _update_collection_indexes(qdrant_service, collection_name, fields_to_update, target_schema)


def upgrade() -> None:
    try:
        asyncio.run(_migrate_indexes(FieldSchema.TEXT))
    except Exception as exc:
        LOGGER.error("Failed to migrate database-source Qdrant text indexes: %s", exc, exc_info=True)
        raise


def downgrade() -> None:
    try:
        asyncio.run(_migrate_indexes(FieldSchema.KEYWORD))
    except Exception as exc:
        LOGGER.error("Failed to downgrade database-source Qdrant text indexes: %s", exc, exc_info=True)
        raise
