"""remove_duplicates_add_pk_chunk_id

Revision ID: a7c91f2e4b0d
Revises: 2b410fd2fb0d
Create Date: 2025-12-05 15:00:00.000000

"""

import logging
from typing import Sequence, Union

from sqlalchemy import inspect, text

from engine.storage_service.local_service import SQLLocalService
from ingestion_script.utils import CHUNK_ID_COLUMN_NAME
from settings import settings

# revision identifiers, used by Alembic.
revision: str = "a7c91f2e4b0d"
down_revision: Union[str, None] = "2b410fd2fb0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
LOGGER = logging.getLogger(__name__)


def get_all_schemas_and_tables(db_service: SQLLocalService):
    """Get all schemas and tables from the database."""
    inspector = inspect(db_service.engine)
    schemas = inspector.get_schema_names()

    schema_tables = {}
    for schema in schemas:
        if schema in ["information_schema", "pg_catalog", "pg_toast"]:
            continue
        tables = inspector.get_table_names(schema=schema)
        if tables:
            schema_tables[schema] = tables

    return schema_tables


def table_has_chunk_id_column(db_service: SQLLocalService, table_name: str, schema_name: str) -> bool:
    try:
        inspector = inspect(db_service.engine)
        columns = [col["name"].lower() for col in inspector.get_columns(table_name, schema=schema_name)]
        return CHUNK_ID_COLUMN_NAME.lower() in columns
    except Exception as e:
        LOGGER.warning(f"Error checking columns for {schema_name}.{table_name}: {str(e)}")
        return False


def table_has_primary_key_on_chunk_id(db_service: SQLLocalService, table_name: str, schema_name: str) -> bool:
    """Check if table has a primary key constraint on chunk_id."""
    try:
        inspector = inspect(db_service.engine)
        pk = inspector.get_pk_constraint(table_name, schema=schema_name) or {}
        constrained = pk.get("constrained_columns") or []
        return CHUNK_ID_COLUMN_NAME in constrained
    except Exception as e:
        LOGGER.warning(f"Error checking primary key for {schema_name}.{table_name}: {str(e)}")
        return False


def remove_duplicates_and_add_pk(db_service: SQLLocalService, table_name: str, schema_name: str) -> bool:
    """Remove duplicate rows and add primary key constraint on chunk_id."""
    try:
        with db_service.engine.begin() as connection:
            # Step 1: Remove duplicates, keeping the first row (lowest ctid) for each chunk_id
            schema = f'"{schema_name}".' if schema_name else ""
            remove_duplicates_sql = text(
                f"""
                WITH ranked AS (
                    SELECT ctid,
                        ROW_NUMBER() OVER (
                            PARTITION BY "{CHUNK_ID_COLUMN_NAME}"
                            ORDER BY ctid
                        ) AS rn
                    FROM {schema}"{table_name}"
                )
                DELETE FROM {schema}"{table_name}" t
                USING ranked r
                WHERE t.ctid = r.ctid
                AND r.rn > 1
                """
            )
            result = connection.execute(remove_duplicates_sql)
            deleted_count = result.rowcount or 0

            if deleted_count > 0:
                LOGGER.info(f"  Deleted {deleted_count} duplicate rows from {schema_name}.{table_name}")

            # Step 2: Check for NULL values in chunk_id
            null_count = connection.execute(
                text(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}" WHERE "{CHUNK_ID_COLUMN_NAME}" IS NULL')
            ).scalar()

            if null_count and null_count > 0:
                LOGGER.error(f"  Cannot add primary key: {null_count} rows have NULL values in {CHUNK_ID_COLUMN_NAME}")
                return False

            # Step 3: Add primary key constraint
            constraint_name = f"{table_name}_{CHUNK_ID_COLUMN_NAME}_pk"
            add_pk_sql = text(
                f'ALTER TABLE "{schema_name}"."{table_name}" '
                f'ADD CONSTRAINT "{constraint_name}" '
                f'PRIMARY KEY ("{CHUNK_ID_COLUMN_NAME}")'
            )
            connection.execute(add_pk_sql)
            LOGGER.info(f"  Added primary key constraint on {CHUNK_ID_COLUMN_NAME}")

            return True

    except Exception as e:
        LOGGER.error(f"  ERROR: Unexpected error processing {schema_name}.{table_name}: {str(e)}")
        import traceback

        LOGGER.error(traceback.format_exc())
        return False


def upgrade() -> None:
    LOGGER.info("=== Starting Migration: Remove Duplicates and Add Primary Key on chunk_id ===\n")

    if not settings.INGESTION_DB_URL:
        LOGGER.error("ERROR: INGESTION_DB_URL is not set in settings")
        LOGGER.error("Please set INGESTION_DB_URL in your environment or credentials.env file")
        return False

    try:
        LOGGER.info("Connecting to ingestion database...")
        db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
        LOGGER.info(f"Connected to database: {db_service.database_name}\n")

        LOGGER.info("Scanning for tables with 'chunk_id' column...")
        schema_tables = get_all_schemas_and_tables(db_service)

        if not schema_tables:
            LOGGER.info("No schemas found in the database")
            return True

        tables_to_migrate = []
        for schema, tables in schema_tables.items():
            for table in tables:
                if table_has_chunk_id_column(db_service, table, schema):
                    if not table_has_primary_key_on_chunk_id(db_service, table, schema):
                        tables_to_migrate.append((schema, table))
                    else:
                        LOGGER.info(f"Skipping {schema}.{table} - already has primary key on {CHUNK_ID_COLUMN_NAME}")

        if not tables_to_migrate:
            LOGGER.info(
                "No tables need migration. All tables either don't have 'chunk_id' or already have primary key on it."
            )
            return True

        LOGGER.info(f"Found {len(tables_to_migrate)} table(s) to migrate:\n")
        for schema, table in tables_to_migrate:
            LOGGER.info(f"  - {schema}.{table}")

        LOGGER.info("\n" + "=" * 60)
        LOGGER.info("Starting migration...\n")

        # Migrate each table
        success_count = 0
        failed_count = 0

        for schema, table in tables_to_migrate:
            LOGGER.info(f"Processing {schema}.{table}...")
            if remove_duplicates_and_add_pk(db_service, table, schema):
                success_count += 1
                LOGGER.info(f"  ✓ Successfully migrated {schema}.{table}\n")
            else:
                failed_count += 1
                LOGGER.error(f"  ✗ Failed to migrate {schema}.{table}\n")

        LOGGER.info("=" * 60)
        LOGGER.info("Migration Summary:")
        LOGGER.info(f"  Successfully migrated: {success_count} table(s)")
        LOGGER.info(f"  Failed: {failed_count} table(s)")
        LOGGER.info("=" * 60)

        return failed_count == 0

    except Exception as e:
        LOGGER.error(f"ERROR: Migration failed with error: {str(e)}")
        import traceback

        LOGGER.error(traceback.format_exc())
        return False


def downgrade() -> None:
    LOGGER.info("No downgrade supported for this migration. Skipping...")
