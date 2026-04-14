#!/usr/bin/env python3
"""Migrate Qdrant collections to hybrid (dense + sparse BM25).

Usage:
    QDRANT_CLUSTER_URL=... QDRANT_API_KEY=... uv run python scripts/migrate_collection_to_hybrid.py <collection>
    uv run python scripts/migrate_collection_to_hybrid.py col_a col_b col_c
"""

import argparse
import asyncio
import logging
import sys
from typing import Any, Optional

from httpx import HTTPStatusError

from engine.qdrant_service import BM25_MODEL, QdrantService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BATCH_SIZE = 250
CONTENT_FIELD = "content"
MAX_RETRIES = 5
RETRY_BASE_DELAY = 5


async def _retry(coro_fn, description: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await coro_fn()
        except HTTPStatusError as e:
            if e.response.status_code in (502, 503, 429) and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * attempt
                print(f"  {description}: {e.response.status_code}, retry {attempt}/{MAX_RETRIES} in {delay}s")
                await asyncio.sleep(delay)
            else:
                raise


async def _scroll_batch(
    service: QdrantService,
    collection_name: str,
    offset: Any = None,
) -> tuple[list[dict], Any]:
    body: dict[str, Any] = {"limit": BATCH_SIZE, "with_payload": True, "with_vector": True}
    if offset is not None:
        body["offset"] = offset

    async def _do():
        return await service._send_request_async(
            method="POST",
            endpoint=f"collections/{collection_name}/points/scroll?wait=true",
            payload=body,
        )

    resp = await _retry(_do, f"[{collection_name}] scroll")
    result = resp.get("result", {})
    return result.get("points", []), result.get("next_page_offset")


def _transform_point(point: dict) -> Optional[dict]:
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


async def _get_vector_config(service: QdrantService, name: str) -> tuple[int, str]:
    info = await service.get_collection_info_async(name)
    vc = info.get("config", {}).get("params", {}).get("vectors", {})
    if "size" in vc:
        return vc["size"], vc.get("distance", "Cosine")
    if "dense" in vc:
        return vc["dense"]["size"], vc["dense"].get("distance", "Cosine")
    raise ValueError(f"Cannot determine vector config for '{name}'")


async def _get_payload_indexes(service: QdrantService, name: str) -> dict[str, Any]:
    info = await service.get_collection_info_async(name)
    return info.get("payload_schema", {})


async def _recreate_indexes(service: QdrantService, name: str, schema: dict[str, Any]) -> None:
    for field_name, field_info in schema.items():
        field_type = (
            field_info.get("data_type") or field_info.get("type") or field_info.get("field_type")
            if isinstance(field_info, dict)
            else field_info
        )
        if field_type:
            print(f"  [{name}] Recreating index: {field_name} ({field_type})")
            try:
                await service._send_request_async(
                    method="PUT",
                    endpoint=f"collections/{name}/index",
                    payload={"field_name": field_name, "field_schema": field_type},
                )
            except Exception as e:
                print(f"  [{name}] WARNING: Failed to recreate index '{field_name}': {e}")


async def migrate_collection(service: QdrantService, name: str) -> bool:
    if not await service.collection_exists_async(name):
        print(f"[{name}] Not found, skipping.")
        return False

    if await service.is_hybrid_collection_async(name):
        print(f"[{name}] Already hybrid, skipping.")
        return True

    vector_size, distance = await _get_vector_config(service, name)
    original_count = await service.count_points_async(name)
    payload_indexes = await _get_payload_indexes(service, name)
    print(
        f"[{name}] {original_count} points, vector_size={vector_size}, "
        f"distance={distance}, indexes={len(payload_indexes)}"
    )

    hybrid_config = {
        "vectors": {"dense": {"size": vector_size, "distance": distance}},
        "sparse_vectors": {"sparse": {"modifier": "idf"}},
    }

    if original_count == 0:
        print(f"[{name}] Empty — recreating as hybrid.")
        await service.delete_collection_async(name)
        resp = await service._send_request_async(
            method="PUT", endpoint=f"collections/{name}?wait=true", payload=hybrid_config
        )
        if "result" not in resp:
            print(f"[{name}] ERROR: Failed to recreate: {resp}")
            return False
        if payload_indexes:
            await _recreate_indexes(service, name, payload_indexes)
        return True

    tmp = f"{name}_hybrid"
    if await service.collection_exists_async(tmp):
        print(f"[{name}] Temp '{tmp}' exists, deleting.")
        await service.delete_collection_async(tmp)

    resp = await service._send_request_async(
        method="PUT", endpoint=f"collections/{tmp}?wait=true", payload=hybrid_config
    )
    if "result" not in resp:
        print(f"[{name}] ERROR: Failed to create temp: {resp}")
        return False

    print(f"[{name}] Copying in batches of {BATCH_SIZE}...")
    migrated = 0
    skipped = 0
    batch_num = 0
    scroll_offset = None

    while True:
        points, scroll_offset = await _scroll_batch(service, name, scroll_offset)
        if not points:
            break

        batch_num += 1
        transformed = [t for p in points if (t := _transform_point(p))]
        skipped += len(points) - len(transformed)

        if transformed:

            async def _do_insert(pts=transformed):
                return await service.insert_points_in_collection_async(pts, tmp)

            try:
                success = await _retry(_do_insert, f"[{name}] insert batch {batch_num}")
            except HTTPStatusError:
                success = False
            if not success:
                print(f"[{name}] ERROR: Batch {batch_num} failed. Cleaning up.")
                await service.delete_collection_async(tmp)
                return False
            migrated += len(transformed)

        print(f"  [{name}] Batch {batch_num}: +{len(transformed)}, total {migrated}/{original_count}")
        if not scroll_offset:
            break

    if skipped > 0:
        print(f"[{name}] WARNING: {skipped} points skipped (missing vector/content). Aborting.")
        await service.delete_collection_async(tmp)
        return False

    tmp_count = await service.count_points_async(tmp)
    if tmp_count != original_count:
        print(f"[{name}] ERROR: Count mismatch: temp={tmp_count}, original={original_count}. Keeping temp.")
        return False

    if payload_indexes:
        await _recreate_indexes(service, tmp, payload_indexes)

    print(f"[{name}] Deleting original and creating alias...")
    await service.delete_collection_async(name)

    alias_resp = await service._send_request_async(
        method="POST",
        endpoint="collections/aliases",
        payload={"actions": [{"create_alias": {"collection_name": tmp, "alias_name": name}}]},
    )
    if "result" not in alias_resp:
        print(f"[{name}] ERROR: Alias failed: {alias_resp}. Data safe in '{tmp}'.")
        return False

    print(f"[{name}] Done! {tmp_count} points (alias '{name}' → '{tmp}').")
    return True


async def main(collection_names: list[str]):
    service = QdrantService.from_defaults()
    succeeded = 0
    failed = 0
    for name in collection_names:
        print(f"\n{'=' * 60}\nMigrating: {name}\n{'=' * 60}")
        if await migrate_collection(service, name):
            succeeded += 1
        else:
            failed += 1

    print(f"\n{'=' * 60}\nResults: {succeeded} succeeded, {failed} failed out of {len(collection_names)}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Qdrant collections to hybrid (dense + sparse BM25)")
    parser.add_argument("collections", nargs="+", help="Collection name(s) to migrate")
    args = parser.parse_args()
    asyncio.run(main(args.collections))
