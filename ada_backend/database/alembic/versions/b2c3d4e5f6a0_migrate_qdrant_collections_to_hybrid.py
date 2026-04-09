"""migrate qdrant collections to hybrid (dense + sparse BM25)

Revision ID: b2c3d4e5f6a0
Revises: a1b2c3d4e5f9
Create Date: 2026-04-03

"""

import asyncio
import logging
from typing import Any, Optional, Sequence, Union

from alembic import op
from sqlalchemy import text

from engine.qdrant_service import BM25_MODEL, QdrantService

revision: str = "b2c3d4e5f6a0"
down_revision: Union[str, None] = "a1b2c3d4e5f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"

LOGGER = logging.getLogger(__name__)

BATCH_SIZE = 100
CONTENT_FIELD = "content"


async def _scroll_with_vectors(
    service: QdrantService,
    collection_name: str,
    batch_size: int = BATCH_SIZE,
) -> list[dict]:
    all_points: list[dict] = []
    offset = None
    while True:
        request_body: dict[str, Any] = {
            "limit": batch_size,
            "with_payload": True,
            "with_vector": True,
        }
        if offset is not None:
            request_body["offset"] = offset
        response = await service._send_request_async(
            method="POST",
            endpoint=f"collections/{collection_name}/points/scroll?wait=true",
            payload=request_body,
        )
        result = response.get("result", {})
        points = result.get("points", [])
        all_points.extend(points)
        offset = result.get("next_page_offset")
        if not offset or not points:
            break
    return all_points


def _transform_point_to_hybrid(point: dict) -> Optional[dict]:
    payload = point.get("payload", {})
    vector = point.get("vector")
    content = payload.get(CONTENT_FIELD, "")

    if not vector or not content:
        return None

    return {
        "id": point["id"],
        "payload": payload,
        "vector": {
            "dense": vector,
            "sparse": {"text": content, "model": BM25_MODEL},
        },
    }


async def _get_vector_config(service: QdrantService, collection_name: str) -> tuple[int, str]:
    info = await service.get_collection_info_async(collection_name)
    vectors_config = info.get("config", {}).get("params", {}).get("vectors", {})
    if "size" in vectors_config:
        return vectors_config["size"], vectors_config.get("distance", "Cosine")
    if "dense" in vectors_config:
        return vectors_config["dense"]["size"], vectors_config["dense"].get("distance", "Cosine")
    raise ValueError(f"Cannot determine vector config for collection '{collection_name}'")


async def _get_payload_indexes(service: QdrantService, collection_name: str) -> dict[str, Any]:
    """Get all payload indexes from a collection."""
    info = await service.get_collection_info_async(collection_name)
    return info.get("payload_schema", {})


async def _recreate_indexes(service: QdrantService, collection_name: str, payload_schema: dict[str, Any]) -> None:
    """Recreate payload indexes on a collection."""
    for field_name, field_info in payload_schema.items():
        # Extract the field type from the schema
        if isinstance(field_info, dict):
            field_type = field_info.get("data_type") or field_info.get("type") or field_info.get("field_type")
        else:
            field_type = field_info

        if field_type:
            LOGGER.info(f"[{collection_name}] Recreating index for field '{field_name}' (type: {field_type})")
            endpoint = f"/collections/{collection_name}/index"
            payload = {"field_name": field_name, "field_schema": field_type}
            try:
                await service._send_request_async(method="PUT", endpoint=endpoint, payload=payload)
            except Exception as e:
                LOGGER.warning(f"[{collection_name}] Failed to recreate index for '{field_name}': {e}")


async def migrate_collection(service: QdrantService, collection_name: str) -> bool:
    is_hybrid = await service.is_hybrid_collection_async(collection_name)
    if is_hybrid:
        LOGGER.info(f"[{collection_name}] Already hybrid, skipping.")
        return True

    LOGGER.info(f"[{collection_name}] Starting migration to hybrid...")

    vector_size, distance = await _get_vector_config(service, collection_name)
    original_count = await service.count_points_async(collection_name)
    payload_indexes = await _get_payload_indexes(service, collection_name)
    LOGGER.info(
        f"[{collection_name}] {original_count} points, vector_size={vector_size}, distance={distance}, "
        f"indexes={len(payload_indexes)}"
    )

    hybrid_payload = {
        "vectors": {"dense": {"size": vector_size, "distance": distance}},
        "sparse_vectors": {"sparse": {"modifier": "idf"}},
    }

    if original_count == 0:
        LOGGER.info(f"[{collection_name}] Empty collection, recreating as hybrid.")
        await service.delete_collection_async(collection_name)
        response = await service._send_request_async(
            method="PUT", endpoint=f"collections/{collection_name}?wait=true", payload=hybrid_payload
        )
        if "result" not in response:
            LOGGER.error(f"[{collection_name}] Failed to recreate empty collection as hybrid: {response}")
            return False
        LOGGER.info(f"[{collection_name}] Recreated as hybrid (empty).")
        if payload_indexes:
            await _recreate_indexes(service, collection_name, payload_indexes)
        return True

    tmp_name = f"{collection_name}__hybrid_tmp"
    if await service.collection_exists_async(tmp_name):
        LOGGER.warning(f"[{collection_name}] Temp collection '{tmp_name}' exists, deleting it.")
        await service.delete_collection_async(tmp_name)

    response = await service._send_request_async(
        method="PUT", endpoint=f"collections/{tmp_name}?wait=true", payload=hybrid_payload
    )
    if "result" not in response:
        LOGGER.error(f"[{collection_name}] Failed to create temp hybrid collection: {response}")
        return False

    LOGGER.info(f"[{collection_name}] Scrolling all points with vectors...")
    all_points = await _scroll_with_vectors(service, collection_name)
    LOGGER.info(f"[{collection_name}] Scrolled {len(all_points)} points.")

    migrated_count = 0
    skipped_count = 0
    for i in range(0, len(all_points), BATCH_SIZE):
        batch = all_points[i : i + BATCH_SIZE]
        transformed = []
        for point in batch:
            new_point = _transform_point_to_hybrid(point)
            if new_point:
                transformed.append(new_point)
            else:
                skipped_count += 1

        if transformed:
            success = await service.insert_points_in_collection_async(transformed, tmp_name)
            if not success:
                LOGGER.error(f"[{collection_name}] Failed to insert batch at offset {i}. Cleaning up temp.")
                await service.delete_collection_async(tmp_name)
                return False
            migrated_count += len(transformed)

    if skipped_count > 0:
        LOGGER.error(
            f"[{collection_name}] {skipped_count} point(s) have missing vector or content. "
            f"Aborting migration to preserve original data. Cleaning up temp collection."
        )
        await service.delete_collection_async(tmp_name)
        return False

    tmp_count = await service.count_points_async(tmp_name)
    if tmp_count != original_count:
        LOGGER.error(
            f"[{collection_name}] Count mismatch: temp has {tmp_count}, expected {original_count}. "
            f"Leaving temp '{tmp_name}' for inspection."
        )
        return False

    if payload_indexes:
        await _recreate_indexes(service, tmp_name, payload_indexes)

    LOGGER.info(f"[{collection_name}] Deleting original and swapping alias to temp hybrid collection...")
    await service.delete_collection_async(collection_name)

    alias_actions = {
        "actions": [
            {"delete_alias": {"alias_name": collection_name}},
            {"create_alias": {"collection_name": tmp_name, "alias_name": collection_name}},
        ]
    }
    response = await service._send_request_async(method="POST", endpoint="collections/aliases", payload=alias_actions)
    if "result" not in response:
        LOGGER.error(f"[{collection_name}] Failed to swap alias: {response}. Data safe in '{tmp_name}'.")
        return False

    LOGGER.info(
        f"[{collection_name}] Migration complete. {tmp_count} points in hybrid collection (alias → '{tmp_name}')."
    )
    return True


async def upgrade_collections(connection, qdrant_service: QdrantService):
    result = connection.execute(
        text("SELECT DISTINCT qdrant_collection_name FROM data_sources WHERE qdrant_collection_name IS NOT NULL")
    )
    collection_names = [row[0] for row in result.fetchall()]

    if not collection_names:
        LOGGER.info("No Qdrant collections found in data_sources.")
        return

    LOGGER.info(f"Found {len(collection_names)} unique collection(s) to check.")

    migrated = 0
    skipped = 0
    failed = 0
    for name in collection_names:
        if not await qdrant_service.collection_exists_async(name):
            LOGGER.warning(f"Collection '{name}' not found in Qdrant, skipping.")
            skipped += 1
            continue
        success = await migrate_collection(qdrant_service, name)
        if success:
            migrated += 1
        else:
            failed += 1

    LOGGER.info(f"Hybrid migration done. Migrated: {migrated}, Skipped: {skipped}, Failed: {failed}")
    if failed > 0:
        raise RuntimeError(
            f"{failed} collection(s) failed hybrid migration (migrated={migrated}, skipped={skipped}). "
            f"Check logs above for per-collection details. "
            f"Temp collections (*__hybrid_tmp) may still exist for manual recovery."
        )


def upgrade() -> None:
    connection = op.get_bind()
    qdrant_service = QdrantService.from_defaults()
    asyncio.run(upgrade_collections(connection, qdrant_service))


def downgrade() -> None:
    LOGGER.info("Downgrade is a no-op. Hybrid collections are backward-compatible with semantic search.")
