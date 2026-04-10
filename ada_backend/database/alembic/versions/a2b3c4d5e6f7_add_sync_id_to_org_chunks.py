"""add_sync_id_to_org_chunks

Revision ID: a2b3c4d5e6f7
Revises: b6c7d8e9f0a1
Create Date: 2026-04-02

"""

import logging
from typing import Sequence, Union

from alembic import op
from sqlalchemy import create_engine, text

from settings import settings

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "b6c7d8e9f0a1"
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


def upgrade() -> None:
    if not settings.INGESTION_DB_URL:
        LOGGER.info("INGESTION_DB_URL is not set. Skipping sync_id migration.")
        return

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

        LOGGER.info(f"Found {len(tables)} org chunk tables to add sync_id column")

        for (table_name,) in tables:
            has_column = ingestion_conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table_name AND column_name = 'sync_id'"
                ),
                {"table_name": table_name},
            ).fetchone()

            if has_column:
                LOGGER.info(f"Table {table_name} already has sync_id column, skipping ADD COLUMN")
            else:
                ingestion_conn.execute(text(f'ALTER TABLE public."{table_name}" ADD COLUMN sync_id VARCHAR'))
                LOGGER.info(f"Added sync_id column to {table_name}")

        backend_conn = op.get_bind()
        db_sources = backend_conn.execute(
            text(
                "SELECT sa.source_id, sa.source_table_name, ds.database_table_name "
                "FROM source_attributes sa "
                "JOIN data_sources ds ON ds.id = sa.source_id "
                "WHERE ds.type = 'database' AND sa.source_table_name IS NOT NULL "
                "AND ds.database_table_name IS NOT NULL"
            )
        ).fetchall()

        if not db_sources:
            LOGGER.info("No database sources found for backfill.")
            return

        LOGGER.info(f"Backfilling sync_id for {len(db_sources)} database sources")

        existing_tables = {t[0] for t in tables}

        for source_id, source_table_name, database_table_name in db_sources:
            if database_table_name not in existing_tables:
                LOGGER.info(f"Table {database_table_name} not found in ingestion DB, skipping source {source_id}")
                continue

            prefix = f"{source_table_name}_"
            prefix_len = len(prefix)
            ingestion_conn.execute(
                text(
                    f'UPDATE public."{database_table_name}" '
                    "SET sync_id = SUBSTRING(file_id FROM :prefix_len + 1) "
                    "WHERE source_id = :source_id AND file_id LIKE :prefix_pattern AND sync_id IS NULL"
                ),
                {
                    "prefix_len": prefix_len,
                    "source_id": str(source_id),
                    "prefix_pattern": f"{prefix}%",
                },
            )

            LOGGER.info(f"Backfilled sync_id for source {source_id} (table: {database_table_name})")

    except Exception as e:
        LOGGER.error(f"Error during sync_id migration: {e}", exc_info=True)
        raise
    finally:
        ingestion_conn.close()
        ingestion_engine.dispose()


def downgrade() -> None:
    if not settings.INGESTION_DB_URL:
        return

    ingestion_engine = create_engine(settings.INGESTION_DB_URL, isolation_level="AUTOCOMMIT")
    ingestion_conn = ingestion_engine.connect()

    try:
        tables = ingestion_conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE 'org_%_chunks'"
            )
        ).fetchall()

        for (table_name,) in tables:
            has_column = ingestion_conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table_name AND column_name = 'sync_id'"
                ),
                {"table_name": table_name},
            ).fetchone()

            if has_column:
                ingestion_conn.execute(text(f'ALTER TABLE public."{table_name}" DROP COLUMN sync_id'))
                LOGGER.info(f"Dropped sync_id column from {table_name}")
    finally:
        ingestion_conn.close()
        ingestion_engine.dispose()
