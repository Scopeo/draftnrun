"""prefix_internal_metadata_keys

Revision ID: d1e2f3a4b5c6
Revises: a3b4c5d6e7f9
Create Date: 2026-05-07 17:17:00.000000

"""

import asyncio
import logging
from typing import Any, Sequence, Union

import psycopg2
from alembic import op
from psycopg2 import sql
from sqlalchemy import text

from engine.qdrant_service import QdrantService
from settings import settings

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "a3b4c5d6e7f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy: Union[str, None] = "breaking"

LOGGER = logging.getLogger(__name__)

BATCH_SIZE = 500
UPGRADE_KEY_RENAMES = {
    "source_url": "_source_url",
    "supabase_url": "_supabase_url",
}
DOWNGRADE_KEY_RENAMES = {value: key for key, value in UPGRADE_KEY_RENAMES.items()}


def _get_data_sources():
    connection = op.get_bind()
    result = connection.execute(
        text(
            """
            SELECT DISTINCT database_schema, database_table_name, qdrant_collection_name
            FROM data_sources
            WHERE database_table_name IS NOT NULL
               OR qdrant_collection_name IS NOT NULL
            """
        )
    )
    return result.fetchall()


def _table_has_metadata_column(cursor, schema_name: str, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name = 'metadata'
        """,
        (schema_name, table_name),
    )
    return cursor.fetchone() is not None


def _rename_metadata_keys_in_ingestion_db(data_sources, key_renames: dict[str, str]) -> None:
    if not settings.INGESTION_DB_URL:
        LOGGER.warning("INGESTION_DB_URL is not set. Skipping ingestion metadata key migration.")
        return

    tables = {
        (source.database_schema, source.database_table_name)
        for source in data_sources
        if source.database_schema and source.database_table_name
    }
    if not tables:
        LOGGER.info("No ingestion tables found for metadata key migration.")
        return

    try:
        ingestion_conn = psycopg2.connect(settings.INGESTION_DB_URL)
        ingestion_conn.autocommit = True
        cursor = ingestion_conn.cursor()

        for schema_name, table_name in tables:
            if not _table_has_metadata_column(cursor, schema_name, table_name):
                LOGGER.warning("Skipping %s.%s because it has no metadata column.", schema_name, table_name)
                continue

            keys_to_remove = sql.SQL(" - ").join(sql.Literal(key) for key in key_renames)
            set_fragments = [
                sql.SQL(
                    "CASE WHEN COALESCE(metadata, '{}'::jsonb) ? {old_key} "
                    "THEN jsonb_build_object({new_key}, metadata -> {old_key}) "
                    "ELSE '{}'::jsonb END"
                ).format(old_key=sql.Literal(old_key), new_key=sql.Literal(new_key))
                for old_key, new_key in key_renames.items()
            ]
            set_expression = sql.SQL(" || ").join([
                sql.SQL("(COALESCE(metadata, '{}'::jsonb) - {keys_to_remove})").format(
                    keys_to_remove=keys_to_remove
                ),
                *set_fragments,
            ])
            where_expression = sql.SQL(" OR ").join(
                sql.SQL("COALESCE(metadata, '{}'::jsonb) ? {old_key}").format(old_key=sql.Literal(old_key))
                for old_key in key_renames
            )
            query = sql.SQL(
                """
                UPDATE {schema_name}.{table_name}
                SET metadata = jsonb_strip_nulls({set_expression})
                WHERE {where_expression}
                """
            ).format(
                schema_name=sql.Identifier(schema_name),
                table_name=sql.Identifier(table_name),
                set_expression=set_expression,
                where_expression=where_expression,
            )
            cursor.execute(query)
            LOGGER.info("Migrated %s metadata rows in %s.%s.", cursor.rowcount, schema_name, table_name)
    except psycopg2.Error as e:
        LOGGER.error("Failed to migrate ingestion DB metadata keys: %s", e, exc_info=True)
        raise
    finally:
        if "cursor" in locals():
            cursor.close()
        if "ingestion_conn" in locals():
            ingestion_conn.close()


async def _scroll_qdrant_batch(
    qdrant_service: QdrantService,
    collection_name: str,
    offset: Any = None,
) -> tuple[list[dict], Any]:
    payload: dict[str, Any] = {"limit": BATCH_SIZE, "with_payload": True, "with_vector": False}
    if offset is not None:
        payload["offset"] = offset
    response = await qdrant_service._send_request_async(
        method="POST",
        endpoint=f"collections/{collection_name}/points/scroll?wait=true",
        payload=payload,
    )
    result = response.get("result", {})
    return result.get("points", []), result.get("next_page_offset")


async def _rename_qdrant_payload_keys_for_collection(
    qdrant_service: QdrantService,
    collection_name: str,
    key_renames: dict[str, str],
) -> int:
    if not await qdrant_service.collection_exists_async(collection_name):
        LOGGER.warning("Qdrant collection %s does not exist. Skipping.", collection_name)
        return 0

    updated_points = 0
    old_keys = list(key_renames.keys())
    offset = None
    while True:
        points, offset = await _scroll_qdrant_batch(qdrant_service, collection_name, offset)
        if not points:
            break

        # Collect all points in this page that need key renames.
        updates: list[tuple[Any, dict]] = []
        for point in points:
            point_payload = point.get("payload") or {}
            renamed_payload = {
                new_key: point_payload[old_key]
                for old_key, new_key in key_renames.items()
                if old_key in point_payload
            }
            if renamed_payload:
                updates.append((point["id"], renamed_payload))

        if updates:
            # Set new keys concurrently (each point may have different values).
            await asyncio.gather(*[
                qdrant_service._send_request_async(
                    method="POST",
                    endpoint=f"collections/{collection_name}/points/payload?wait=true",
                    payload={"points": [point_id], "payload": renamed_payload},
                )
                for point_id, renamed_payload in updates
            ])
            # Delete old keys in a single batch request for all affected points.
            affected_ids = [point_id for point_id, _ in updates]
            await qdrant_service._send_request_async(
                method="POST",
                endpoint=f"collections/{collection_name}/points/payload/delete?wait=true",
                payload={"points": affected_ids, "keys": old_keys},
            )
            updated_points += len(updates)

        if offset is None:
            break

    LOGGER.info("Migrated %s Qdrant points in collection %s.", updated_points, collection_name)
    return updated_points


async def _rename_qdrant_payload_keys(data_sources, key_renames: dict[str, str]) -> None:
    collection_names = sorted({
        source.qdrant_collection_name for source in data_sources if source.qdrant_collection_name
    })
    if not collection_names:
        LOGGER.info("No Qdrant collections found for metadata key migration.")
        return

    qdrant_service = QdrantService.from_defaults(timeout=120)
    total_updated = 0
    for collection_name in collection_names:
        total_updated += await _rename_qdrant_payload_keys_for_collection(
            qdrant_service,
            collection_name,
            key_renames,
        )
    LOGGER.info("Migrated %s total Qdrant points.", total_updated)


def _rename_internal_metadata_keys(key_renames: dict[str, str]) -> None:
    data_sources = _get_data_sources()
    if not data_sources:
        LOGGER.info("No data sources found for metadata key migration.")
        return

    _rename_metadata_keys_in_ingestion_db(data_sources, key_renames)
    asyncio.run(_rename_qdrant_payload_keys(data_sources, key_renames))


def upgrade() -> None:
    _rename_internal_metadata_keys(UPGRADE_KEY_RENAMES)


def downgrade() -> None:
    _rename_internal_metadata_keys(DOWNGRADE_KEY_RENAMES)
