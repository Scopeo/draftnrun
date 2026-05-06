"""migrate_db_source_chunk_ids_to_uuid

Revision ID: c7d8e9f0a1b2
Revises: a3b4c5d6e7f9
Create Date: 2026-04-27

"""

import logging
import uuid
from typing import Sequence, Union
from uuid import uuid4

import httpx
from alembic import op
from sqlalchemy import create_engine, text

from settings import settings

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "a3b4c5d6e7f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"

LOGGER = logging.getLogger("alembic.migration")
LOGGER.setLevel(logging.DEBUG)

if not LOGGER.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(levelname)-5.5s [%(name)s] %(message)s")
    console_handler.setFormatter(formatter)
    LOGGER.addHandler(console_handler)
    LOGGER.propagate = False

UUID_REGEX = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
MIGRATION_LOG_TABLE = "_chunk_id_migration_log"
DB_BATCH_SIZE = 500
QDRANT_SCROLL_BATCH = 100
QDRANT_UPSERT_BATCH = 50


def _batch_update_db(ingestion_conn, table_name: str, mapping: list[tuple[str, str, str]]):
    for i in range(0, len(mapping), DB_BATCH_SIZE):
        batch = mapping[i : i + DB_BATCH_SIZE]
        values_parts = []
        params = {}
        for idx, (old_cid, sid, new_uuid) in enumerate(batch):
            values_parts.append(f"(:old_{idx}, CAST(:sid_{idx} AS uuid), :new_{idx})")
            params[f"old_{idx}"] = old_cid
            params[f"sid_{idx}"] = sid
            params[f"new_{idx}"] = new_uuid
        values_sql = ", ".join(values_parts)
        ingestion_conn.execute(
            text(
                f'UPDATE public."{table_name}" AS t '
                f"SET chunk_id = v.new_uuid "
                f"FROM (VALUES {values_sql}) AS v(old_cid, sid, new_uuid) "
                f"WHERE t.chunk_id = v.old_cid AND t.source_id = v.sid"
            ),
            params,
        )
        LOGGER.info(f"  DB batch {i // DB_BATCH_SIZE + 1}: updated {len(batch)} rows")


def _upsert_points(client: httpx.Client, qdrant_url: str, headers: dict, collection_name: str, points: list[dict]):
    for i in range(0, len(points), QDRANT_UPSERT_BATCH):
        batch = points[i : i + QDRANT_UPSERT_BATCH]
        client.put(
            f"{qdrant_url}/collections/{collection_name}/points?wait=true",
            headers=headers,
            json={"points": batch},
        ).raise_for_status()


def _delete_points(client: httpx.Client, qdrant_url: str, headers: dict, collection_name: str, point_ids: list):
    for i in range(0, len(point_ids), QDRANT_UPSERT_BATCH):
        batch = point_ids[i : i + QDRANT_UPSERT_BATCH]
        client.post(
            f"{qdrant_url}/collections/{collection_name}/points/delete?wait=true",
            headers=headers,
            json={"points": batch},
        ).raise_for_status()


def _legacy_point_id(source_id: str, chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_id}:{chunk_id}"))


def _scroll_and_replace_qdrant_points(
    client: httpx.Client,
    qdrant_url: str,
    headers: dict,
    collection_name: str,
    chunk_id_map: dict[str, str],
    build_point_id=None,
):
    if build_point_id is None:
        def build_point_id(cid):
            return cid

    offset = None
    replaced = 0
    page_num = 0

    while True:
        scroll_body: dict = {
            "limit": QDRANT_SCROLL_BATCH,
            "with_payload": True,
            "with_vector": True,
        }
        if offset is not None:
            scroll_body["offset"] = offset

        resp = client.post(
            f"{qdrant_url}/collections/{collection_name}/points/scroll",
            headers=headers,
            json=scroll_body,
        )
        resp.raise_for_status()
        result = resp.json().get("result", {})
        points = result.get("points", [])

        if not points:
            if page_num == 0:
                LOGGER.warning(f"    Qdrant scroll returned 0 points in collection={collection_name}")
            break

        page_num += 1
        sample_cids = [p.get("payload", {}).get("chunk_id") for p in points[:5]]
        LOGGER.info(
            f"    Qdrant scroll page {page_num}: {len(points)} points. "
            f"Sample chunk_ids: {sample_cids}"
        )

        new_points = []
        old_ids = []
        for point in points:
            cur_cid = point.get("payload", {}).get("chunk_id")
            new_cid = chunk_id_map.get(cur_cid)
            if new_cid is None:
                continue

            payload = dict(point.get("payload", {}))
            payload["chunk_id"] = new_cid
            new_points.append({
                "id": build_point_id(new_cid),
                "payload": payload,
                "vector": point["vector"],
            })
            old_ids.append(point["id"])

        if new_points:
            _upsert_points(client, qdrant_url, headers, collection_name, new_points)
            _delete_points(client, qdrant_url, headers, collection_name, old_ids)

        replaced += len(new_points)
        LOGGER.info(
            f"    Qdrant collection {collection_name} page {page_num}: "
            f"{len(new_points)}/{len(points)} replaced, {replaced} total"
        )

        offset = result.get("next_page_offset")
        if offset is None:
            break

    return replaced


def upgrade() -> None:
    if not settings.INGESTION_DB_URL:
        LOGGER.info("INGESTION_DB_URL not set. Skipping chunk_id UUID migration.")
        return

    backend_conn = op.get_bind()
    db_source_rows = backend_conn.execute(
        text("SELECT id::text, qdrant_collection_name FROM data_sources WHERE type = 'database'")
    ).fetchall()
    db_source_ids = {row[0] for row in db_source_rows}
    source_to_collection = {sid: col for sid, col in db_source_rows if col is not None}

    if not db_source_ids:
        LOGGER.info("No database-type sources found. Nothing to migrate.")
        return

    LOGGER.info(f"Found {len(db_source_ids)} database-type sources")
    for sid, col in db_source_rows:
        LOGGER.info(f"  source {sid} -> qdrant_collection_name={col!r}")
    LOGGER.info(f"Sources with non-null collection name: {len(source_to_collection)}")

    ingestion_engine = create_engine(settings.INGESTION_DB_URL, isolation_level="AUTOCOMMIT")
    ingestion_conn = ingestion_engine.connect()

    try:
        tables = ingestion_conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE 'org_%_chunks'"
            )
        ).fetchall()

        if not tables:
            LOGGER.info("No org chunk tables found. Nothing to migrate.")
            return

        source_ids_sql = ", ".join(f"'{sid}'" for sid in db_source_ids)
        all_mappings: dict[str, list[tuple[str, str, str]]] = {}

        for (table_name,) in tables:
            has_source_id = ingestion_conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :tn AND column_name = 'source_id'"
                ),
                {"tn": table_name},
            ).fetchone()

            if not has_source_id:
                LOGGER.info(f"Table {table_name} has no source_id column, skipping")
                continue

            rows = ingestion_conn.execute(
                text(
                    f'SELECT chunk_id, source_id::text FROM public."{table_name}" '
                    f"WHERE source_id::text IN ({source_ids_sql}) AND chunk_id !~* '{UUID_REGEX}'"
                )
            ).fetchall()

            if not rows:
                LOGGER.info(f"Table {table_name}: no non-UUID chunk_ids found for database sources")
                continue

            table_mapping = [(old_cid, sid, str(uuid4())) for old_cid, sid in rows]
            all_mappings[table_name] = table_mapping
            LOGGER.info(f"Table {table_name}: {len(table_mapping)} chunk_ids to migrate")

        if not all_mappings:
            LOGGER.info("No non-UUID chunk_ids found across any table. Migration complete.")
            return

        ingestion_conn.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS public.{MIGRATION_LOG_TABLE} ("
                "  table_name VARCHAR NOT NULL,"
                "  old_chunk_id VARCHAR NOT NULL,"
                "  source_id VARCHAR NOT NULL,"
                "  new_chunk_id VARCHAR NOT NULL"
                ")"
            )
        )
        for table_name, mapping in all_mappings.items():
            for i in range(0, len(mapping), DB_BATCH_SIZE):
                batch = mapping[i : i + DB_BATCH_SIZE]
                values_parts = []
                params = {}
                for idx, (old_cid, sid, new_uuid) in enumerate(batch):
                    values_parts.append(f"(:tn_{idx}, :old_{idx}, :sid_{idx}, :new_{idx})")
                    params[f"tn_{idx}"] = table_name
                    params[f"old_{idx}"] = old_cid
                    params[f"sid_{idx}"] = sid
                    params[f"new_{idx}"] = new_uuid
                ingestion_conn.execute(
                    text(
                        f"INSERT INTO public.{MIGRATION_LOG_TABLE} "
                        f"(table_name, old_chunk_id, source_id, new_chunk_id) "
                        f"VALUES {', '.join(values_parts)}"
                    ),
                    params,
                )
        LOGGER.info(f"Saved migration log ({sum(len(m) for m in all_mappings.values())} entries)")

        LOGGER.info("Phase 1: Updating ingestion DB...")
        for table_name, mapping in all_mappings.items():
            _batch_update_db(ingestion_conn, table_name, mapping)
            LOGGER.info(f"Finished DB update for {table_name} ({len(mapping)} rows)")

        if not settings.QDRANT_CLUSTER_URL or not settings.QDRANT_API_KEY:
            LOGGER.info("QDRANT_CLUSTER_URL or QDRANT_API_KEY not set. Skipping Qdrant payload update.")
            return

        if not source_to_collection:
            LOGGER.info("No DB sources with Qdrant collections found. Skipping Qdrant update.")
            return

        LOGGER.info("Phase 2: Replacing Qdrant points with new IDs...")
        qdrant_url = settings.QDRANT_CLUSTER_URL.rstrip("/")
        headers = {"api-key": settings.QDRANT_API_KEY, "Content-Type": "application/json"}

        log_rows = ingestion_conn.execute(
            text(f"SELECT old_chunk_id, source_id, new_chunk_id FROM public.{MIGRATION_LOG_TABLE}")
        ).fetchall()

        collection_chunk_maps: dict[str, dict[str, str]] = {}
        for old_cid, sid, new_uuid in log_rows:
            col = source_to_collection.get(sid)
            if col:
                collection_chunk_maps.setdefault(col, {})[old_cid] = new_uuid
        LOGGER.info(
            f"Migration log: {len(log_rows)} entries, "
            f"{len(collection_chunk_maps)} collections to update"
        )
        for col, cmap in collection_chunk_maps.items():
            sample = list(cmap.items())[:3]
            LOGGER.info(f"  collection {col}: {len(cmap)} mappings, sample: {sample}")

        with httpx.Client(timeout=60) as qdrant_client:
            resp = qdrant_client.get(f"{qdrant_url}/collections", headers=headers)
            resp.raise_for_status()
            existing_collections = {c["name"] for c in resp.json().get("result", {}).get("collections", [])}
            LOGGER.info(f"Qdrant has {len(existing_collections)} collections: {existing_collections}")

            total_replaced = 0

            for collection_name, chunk_id_map in collection_chunk_maps.items():
                if collection_name not in existing_collections:
                    LOGGER.info(
                        f"  Collection '{collection_name}' not found in Qdrant, "
                        f"skipping {len(chunk_id_map)} chunks"
                    )
                    continue

                LOGGER.info(
                    f"  Collection '{collection_name}': replacing points "
                    f"({len(chunk_id_map)} chunks to migrate)"
                )
                replaced = _scroll_and_replace_qdrant_points(
                    qdrant_client, qdrant_url, headers, collection_name, chunk_id_map,
                )
                total_replaced += replaced
                LOGGER.info(f"  Collection '{collection_name}': {replaced} Qdrant points replaced")

        LOGGER.info(f"Qdrant update complete: {total_replaced} replaced")

    except Exception as e:
        LOGGER.error(f"Error during chunk_id UUID migration: {e}", exc_info=True)
        raise
    finally:
        ingestion_conn.close()
        ingestion_engine.dispose()


def downgrade() -> None:
    if not settings.INGESTION_DB_URL:
        LOGGER.info("INGESTION_DB_URL not set. Skipping downgrade.")
        return

    ingestion_engine = create_engine(settings.INGESTION_DB_URL, isolation_level="AUTOCOMMIT")
    ingestion_conn = ingestion_engine.connect()

    try:
        log_exists = ingestion_conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                f"WHERE table_schema = 'public' AND table_name = '{MIGRATION_LOG_TABLE}'"
            )
        ).fetchone()

        if not log_exists:
            LOGGER.info(f"Migration log table {MIGRATION_LOG_TABLE} not found. Cannot downgrade.")
            return

        log_rows = ingestion_conn.execute(
            text(f"SELECT table_name, old_chunk_id, source_id, new_chunk_id FROM public.{MIGRATION_LOG_TABLE}")
        ).fetchall()

        if not log_rows:
            LOGGER.info("Migration log is empty. Nothing to downgrade.")
            return

        all_mappings: dict[str, list[tuple[str, str, str]]] = {}
        for table_name, old_cid, sid, new_uuid in log_rows:
            all_mappings.setdefault(table_name, []).append((new_uuid, sid, old_cid))

        LOGGER.info(f"Loaded {len(log_rows)} entries from migration log")

        LOGGER.info("Phase 1: Reverting ingestion DB...")
        for table_name, mapping in all_mappings.items():
            _batch_update_db(ingestion_conn, table_name, mapping)
            LOGGER.info(f"Finished DB revert for {table_name} ({len(mapping)} rows)")

        if not settings.QDRANT_CLUSTER_URL or not settings.QDRANT_API_KEY:
            LOGGER.info("QDRANT_CLUSTER_URL or QDRANT_API_KEY not set. Skipping Qdrant revert.")
        else:
            LOGGER.info("Phase 2: Reverting Qdrant points to legacy IDs...")
            qdrant_url = settings.QDRANT_CLUSTER_URL.rstrip("/")
            headers = {"api-key": settings.QDRANT_API_KEY, "Content-Type": "application/json"}

            backend_conn = op.get_bind()
            db_sources = backend_conn.execute(
                text(
                    "SELECT id::text, qdrant_collection_name FROM data_sources "
                    "WHERE type = 'database' AND qdrant_collection_name IS NOT NULL"
                )
            ).fetchall()

            source_to_collection = {sid: col for sid, col in db_sources}

            collection_chunk_maps: dict[str, dict[str, str]] = {}
            old_cid_to_source: dict[str, str] = {}
            for mapping in all_mappings.values():
                for new_uuid, sid, old_cid in mapping:
                    col = source_to_collection.get(sid)
                    if col:
                        collection_chunk_maps.setdefault(col, {})[new_uuid] = old_cid
                        old_cid_to_source[old_cid] = sid

            def _legacy_build_point_id(cid):
                sid = old_cid_to_source.get(cid)
                if sid:
                    return _legacy_point_id(sid, cid)
                return cid

            with httpx.Client(timeout=60) as qdrant_client:
                resp = qdrant_client.get(f"{qdrant_url}/collections", headers=headers)
                resp.raise_for_status()
                existing_collections = {c["name"] for c in resp.json().get("result", {}).get("collections", [])}

                total_reverted = 0
                for collection_name, chunk_id_map in collection_chunk_maps.items():
                    if collection_name not in existing_collections:
                        continue

                    LOGGER.info(
                        f"  Collection '{collection_name}': reverting {len(chunk_id_map)} points"
                    )
                    reverted = _scroll_and_replace_qdrant_points(
                        qdrant_client, qdrant_url, headers, collection_name, chunk_id_map,
                        build_point_id=_legacy_build_point_id,
                    )
                    total_reverted += reverted
                    LOGGER.info(f"  Collection '{collection_name}': {reverted} Qdrant points reverted")

            LOGGER.info(f"Qdrant revert complete: {total_reverted} points reverted")

        ingestion_conn.execute(text(f"DROP TABLE IF EXISTS public.{MIGRATION_LOG_TABLE}"))
        LOGGER.info(f"Dropped migration log table {MIGRATION_LOG_TABLE}")

    except Exception as e:
        LOGGER.error(f"Error during chunk_id UUID downgrade: {e}", exc_info=True)
        raise
    finally:
        ingestion_conn.close()
        ingestion_engine.dispose()
