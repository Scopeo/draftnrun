"""migrate_db_source_chunk_ids_to_uuid

Revision ID: c7d8e9f0a1b2
Revises: l3m4n5o6p7q8
Create Date: 2026-04-27

"""

import logging
from typing import Sequence, Union
from uuid import uuid4

import httpx
from alembic import op
from sqlalchemy import create_engine, text

from settings import settings

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "l3m4n5o6p7q8"
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
QDRANT_SCROLL_BATCH = 256


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


def _scroll_and_update_qdrant(
    client: httpx.Client,
    qdrant_url: str,
    headers: dict,
    collection_name: str,
    source_id: str,
    chunk_id_map: dict[str, str],
):
    offset = None
    updated = 0
    failed_ids: list[str] = []
    page_num = 0

    while True:
        scroll_body: dict = {
            "limit": QDRANT_SCROLL_BATCH,
            "with_payload": ["chunk_id", "source_id"],
            "with_vector": False,
            "filter": {"must": [{"key": "source_id", "match": {"value": source_id}}]},
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
            break

        page_num += 1
        page_updated = 0
        page_failed = 0

        for point in points:
            old_cid = point.get("payload", {}).get("chunk_id")
            new_cid = chunk_id_map.get(old_cid)
            if new_cid is None:
                continue
            try:
                client.post(
                    f"{qdrant_url}/collections/{collection_name}/points/payload",
                    headers=headers,
                    json={"payload": {"chunk_id": new_cid}, "points": [point["id"]]},
                ).raise_for_status()
                page_updated += 1
            except httpx.HTTPStatusError as exc:
                LOGGER.warning(
                    f"    Qdrant set_payload failed for point {point['id']} "
                    f"(source {source_id}): {exc.response.status_code}"
                )
                failed_ids.append(str(point["id"]))
                page_failed += 1

        updated += page_updated
        LOGGER.info(
            f"    Qdrant source {source_id} page {page_num}: "
            f"{page_updated} updated, {page_failed} failed, {updated} total"
        )

        offset = result.get("next_page_offset")
        if offset is None:
            break

    if failed_ids:
        LOGGER.warning(f"    Qdrant source {source_id}: {len(failed_ids)} points failed: {failed_ids[:20]}")

    return updated


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

        LOGGER.info("Phase 2: Updating Qdrant payloads...")
        qdrant_url = settings.QDRANT_CLUSTER_URL.rstrip("/")
        headers = {"api-key": settings.QDRANT_API_KEY, "Content-Type": "application/json"}

        source_chunk_maps: dict[str, dict[str, str]] = {}
        log_rows = ingestion_conn.execute(
            text(f"SELECT old_chunk_id, source_id, new_chunk_id FROM public.{MIGRATION_LOG_TABLE}")
        ).fetchall()
        for old_cid, sid, new_uuid in log_rows:
            source_chunk_maps.setdefault(sid, {})[old_cid] = new_uuid

        with httpx.Client(timeout=60) as qdrant_client:
            resp = qdrant_client.get(f"{qdrant_url}/collections", headers=headers)
            resp.raise_for_status()
            existing_collections = {c["name"] for c in resp.json().get("result", {}).get("collections", [])}

            total_updated = 0
            total_skipped = 0

            for source_id, chunk_id_map in source_chunk_maps.items():
                collection_name = source_to_collection.get(source_id)
                if not collection_name or collection_name not in existing_collections:
                    total_skipped += len(chunk_id_map)
                    LOGGER.info(
                        f"  Source {source_id}: collection '{collection_name}' not found, "
                        f"skipping {len(chunk_id_map)} chunks"
                    )
                    continue

                LOGGER.info(
                    f"  Source {source_id}: scrolling collection '{collection_name}' "
                    f"({len(chunk_id_map)} chunks to update)"
                )
                updated = _scroll_and_update_qdrant(
                    qdrant_client, qdrant_url, headers, collection_name, source_id, chunk_id_map
                )
                total_updated += updated
                LOGGER.info(f"  Source {source_id}: {updated} Qdrant points updated")

        LOGGER.info(f"Qdrant update complete: {total_updated} updated, {total_skipped} skipped")

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
            LOGGER.info("Phase 2: Reverting Qdrant payloads...")
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

            source_chunk_maps: dict[str, dict[str, str]] = {}
            for mapping in all_mappings.values():
                for new_uuid, sid, old_cid in mapping:
                    source_chunk_maps.setdefault(sid, {})[new_uuid] = old_cid

            with httpx.Client(timeout=60) as qdrant_client:
                resp = qdrant_client.get(f"{qdrant_url}/collections", headers=headers)
                resp.raise_for_status()
                existing_collections = {c["name"] for c in resp.json().get("result", {}).get("collections", [])}

                total_updated = 0
                for source_id, chunk_id_map in source_chunk_maps.items():
                    collection_name = source_to_collection.get(source_id)
                    if not collection_name or collection_name not in existing_collections:
                        continue

                    LOGGER.info(
                        f"  Source {source_id}: reverting {len(chunk_id_map)} chunks in collection '{collection_name}'"
                    )
                    updated = _scroll_and_update_qdrant(
                        qdrant_client, qdrant_url, headers, collection_name, source_id, chunk_id_map
                    )
                    total_updated += updated
                    LOGGER.info(f"  Source {source_id}: {updated} Qdrant points reverted")

            LOGGER.info(f"Qdrant revert complete: {total_updated} points reverted")

        ingestion_conn.execute(text(f"DROP TABLE IF EXISTS public.{MIGRATION_LOG_TABLE}"))
        LOGGER.info(f"Dropped migration log table {MIGRATION_LOG_TABLE}")

    except Exception as e:
        LOGGER.error(f"Error during chunk_id UUID downgrade: {e}", exc_info=True)
        raise
    finally:
        ingestion_conn.close()
        ingestion_engine.dispose()
