"""migrate qdrant collections to hybrid in place (existing dense + sparse BM25)

Revision ID: b2c3d4e5f6a0
Revises: 4071a252013a
Create Date: 2026-04-03
"""

import asyncio
import logging
from typing import Any, Optional, Sequence, Union

from alembic import op
from httpx import HTTPStatusError
from sqlalchemy import text

from engine.qdrant_service import BM25_MODEL, QdrantService

revision: str = "b2c3d4e5f6a0"
down_revision: Union[str, None] = "4071a252013a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"

LOGGER = logging.getLogger(__name__)

BATCH_SIZE = 100
CONTENT_FIELD = "content"
SPARSE_VECTOR_NAME = "sparse"
MAX_RETRIES = 5
RETRY_BASE_DELAY = 5


async def _retry_async(coro_fn, description: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await coro_fn()
        except HTTPStatusError as e:
            if e.response.status_code in (502, 503, 429) and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * attempt
                LOGGER.warning(
                    "%s: %s, retry %s/%s in %ss", description, e.response.status_code, attempt, MAX_RETRIES, delay
                )
                await asyncio.sleep(delay)
            else:
                raise


async def _scroll_batch_for_sparse_backfill(
    service: QdrantService,
    collection_name: str,
    offset: Any = None,
    batch_size: int = BATCH_SIZE,
) -> tuple[list[dict[str, Any]], Any]:
    request_body: dict[str, Any] = {
        "limit": batch_size,
        "with_payload": [CONTENT_FIELD],
        "with_vector": False,
    }
    if offset is not None:
        request_body["offset"] = offset

    async def _do_scroll():
        return await service._send_request_async(
            method="POST",
            endpoint=f"collections/{collection_name}/points/scroll?wait=true",
            payload=request_body,
        )

    response = await _retry_async(_do_scroll, f"[{collection_name}] scroll")
    result = response.get("result", {})
    return result.get("points", []), result.get("next_page_offset")


async def _ensure_sparse_vector_config(
    service: QdrantService,
    collection_name: str,
) -> None:
    collection_info = await service.get_collection_info_async(collection_name)
    sparse_vectors = collection_info.get("config", {}).get("params", {}).get("sparse_vectors")

    if isinstance(sparse_vectors, dict) and SPARSE_VECTOR_NAME in sparse_vectors:
        LOGGER.info("[%s] Sparse vector config already exists.", collection_name)
        return

    payload = {"sparse_vectors": {SPARSE_VECTOR_NAME: {"modifier": "idf"}}}

    async def _do_patch():
        return await service._send_request_async(
            method="PATCH",
            endpoint=f"collections/{collection_name}",
            payload=payload,
        )

    response = await _retry_async(_do_patch, f"[{collection_name}] add sparse config")
    if "result" not in response:
        raise RuntimeError(f"[{collection_name}] Failed to add sparse vector config: {response}")

    LOGGER.info("[%s] Added sparse vector config.", collection_name)


def _build_sparse_vector_update(point: dict[str, Any]) -> Optional[dict[str, Any]]:
    payload = point.get("payload") or {}
    content = payload.get(CONTENT_FIELD)

    if not isinstance(content, str):
        return None

    content = content.strip()
    if not content:
        return None

    return {
        "id": point["id"],
        "vector": {SPARSE_VECTOR_NAME: {"text": content, "model": BM25_MODEL}},
    }


async def _update_sparse_vectors(
    service: QdrantService,
    collection_name: str,
    point_updates: list[dict[str, Any]],
) -> None:
    if not point_updates:
        return

    async def _do_update():
        return await service._send_request_async(
            method="PUT",
            endpoint=f"collections/{collection_name}/points/vectors?wait=true",
            payload={"points": point_updates},
        )

    response = await _retry_async(_do_update, f"[{collection_name}] update vectors")
    if "result" not in response:
        raise RuntimeError(f"[{collection_name}] Failed sparse vector batch update: {response}")


async def migrate_collection(service: QdrantService, collection_name: str) -> bool:
    try:
        is_hybrid = await service.is_hybrid_collection_async(collection_name)
        if is_hybrid:
            LOGGER.info("[%s] Already hybrid, skipping.", collection_name)
            return True

        original_count = await service.count_points_async(collection_name)
        LOGGER.info(
            "[%s] Starting in-place sparse backfill. points=%s, batch_size=%s",
            collection_name, original_count, BATCH_SIZE,
        )

        await _ensure_sparse_vector_config(service, collection_name)

        if original_count == 0:
            LOGGER.info("[%s] Empty collection, sparse config added.", collection_name)
            return True

        migrated_count = 0
        skipped_count = 0
        batch_num = 0
        scroll_offset = None

        while True:
            points, scroll_offset = await _scroll_batch_for_sparse_backfill(
                service=service, collection_name=collection_name, offset=scroll_offset, batch_size=BATCH_SIZE,
            )
            if not points:
                break

            batch_num += 1
            updates: list[dict[str, Any]] = []

            for point in points:
                update = _build_sparse_vector_update(point)
                if update is None:
                    skipped_count += 1
                    continue
                updates.append(update)

            if updates:
                await _update_sparse_vectors(service=service, collection_name=collection_name, point_updates=updates)
                migrated_count += len(updates)

            LOGGER.info(
                "[%s] Batch %s: updated=%s, skipped=%s, total_updated=%s",
                collection_name, batch_num, len(updates), skipped_count, migrated_count,
            )

            if scroll_offset is None:
                break

        LOGGER.info(
            "[%s] In-place hybrid migration complete. updated=%s skipped=%s total=%s",
            collection_name, migrated_count, skipped_count, original_count,
        )
        return True

    except Exception as exc:
        LOGGER.exception("[%s] Hybrid migration failed: %s", collection_name, exc)
        return False


async def upgrade_collections(connection, qdrant_service: QdrantService) -> None:
    result = connection.execute(
        text("SELECT DISTINCT qdrant_collection_name FROM data_sources WHERE qdrant_collection_name IS NOT NULL")
    )
    collection_names = [row[0] for row in result.fetchall()]

    if not collection_names:
        LOGGER.info("No Qdrant collections found in data_sources.")
        return

    LOGGER.info("Found %s unique collection(s) to check.", len(collection_names))

    migrated = 0
    skipped = 0
    failed = 0

    for name in collection_names:
        if not await qdrant_service.collection_exists_async(name):
            LOGGER.warning("Collection '%s' not found in Qdrant, skipping.", name)
            skipped += 1
            continue

        success = await migrate_collection(qdrant_service, name)
        if success:
            migrated += 1
        else:
            failed += 1

    LOGGER.info("Hybrid in-place migration done. Migrated: %s, Skipped: %s, Failed: %s", migrated, skipped, failed)

    if failed > 0:
        raise RuntimeError(
            f"{failed} collection(s) failed hybrid migration (migrated={migrated}, skipped={skipped}). "
            f"Check logs above."
        )


def upgrade() -> None:
    connection = op.get_bind()
    qdrant_service = QdrantService.from_defaults()
    asyncio.run(upgrade_collections(connection, qdrant_service))


def downgrade() -> None:
    LOGGER.info("Downgrade is a no-op. Hybrid collections are backward-compatible.")
