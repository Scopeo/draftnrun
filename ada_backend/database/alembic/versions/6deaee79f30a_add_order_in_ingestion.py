"""add_order_in_ingestion

Revision ID: 6deaee79f30a
Revises: 7f2bae4dea37
Create Date: 2025-12-03 11:42:07.921159

"""

import logging
from typing import Sequence, Union
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError

from engine.storage_service.local_service import SQLLocalService
from data_ingestion.utils import ORDER_COLUMN_NAME
from ingestion_script.utils import CHUNK_ID_COLUMN_NAME
from settings import settings


# revision identifiers, used by Alembic.
revision: str = "6deaee79f30a"
down_revision: Union[str, None] = "7f2bae4dea37"
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


def table_has_order_column(db_service: SQLLocalService, table_name: str, schema_name: str) -> bool:
    try:
        inspector = inspect(db_service.engine)
        columns = [col["name"].lower() for col in inspector.get_columns(table_name, schema=schema_name)]
        return ORDER_COLUMN_NAME.lower() in columns
    except Exception as e:
        LOGGER.warning(f"Error checking columns for {schema_name}.{table_name}: {str(e)}")
        return False


def add_order_column_to_table(db_service: SQLLocalService, table_name: str, schema_name: str) -> bool:
    try:
        with db_service.engine.connect() as connection:
            if table_has_order_column(db_service, table_name, schema_name):
                LOGGER.info(f"  Table {schema_name}.{table_name} already has '{ORDER_COLUMN_NAME}' column, skipping")
                return True

            LOGGER.info(f"  Adding '{ORDER_COLUMN_NAME}' column to {schema_name}.{table_name}...")
            add_column_sql = text(
                f'ALTER TABLE "{schema_name}"."{table_name}" ' f'ADD COLUMN "{ORDER_COLUMN_NAME}" INTEGER'
            )
            connection.execute(add_column_sql)
            connection.commit()

            # Step 2: Populate the order column from chunk_id
            # Extract the last part after the last underscore, convert to int, subtract 1
            # chunk_id format: <prefix>_<index> where index is typically 1-based
            # order should be 0-based, so we subtract 1
            # Handle cases where the last part might not be numeric (e.g., Excel sheets)
            LOGGER.info(f"  Populating '{ORDER_COLUMN_NAME}' column from {CHUNK_ID_COLUMN_NAME}...")
            update_sql = text(
                f"""
                UPDATE "{schema_name}"."{table_name}"
                SET "{ORDER_COLUMN_NAME}" = (
                    CASE 
                        WHEN "{CHUNK_ID_COLUMN_NAME}" LIKE '%_%' 
                             AND SPLIT_PART("{CHUNK_ID_COLUMN_NAME}", '_', -1) ~ '^[0-9]+$'
                        THEN GREATEST(
                            0,
                            CAST(
                                SPLIT_PART("{CHUNK_ID_COLUMN_NAME}", '_', -1) AS INTEGER
                            ) - 1
                        )
                        ELSE NULL
                    END
                )
                WHERE "{CHUNK_ID_COLUMN_NAME}" IS NOT NULL
                """
            )
            result = connection.execute(update_sql)
            rows_updated = result.rowcount
            connection.commit()
            LOGGER.info(f"  Updated {rows_updated} rows in {schema_name}.{table_name}")

            return True

    except SQLAlchemyError as e:
        LOGGER.error(f"  ERROR: Failed to add order column to {schema_name}.{table_name}: {str(e)}")
        return False
    except Exception as e:
        LOGGER.error(f"  ERROR: Unexpected error processing {schema_name}.{table_name}: {str(e)}")
        return False


def upgrade() -> None:
    LOGGER.info("=== Starting Migration: Add 'order' Column to Ingestion Tables ===\n")

    if not settings.INGESTION_DB_URL:
        LOGGER.error("ERROR: INGESTION_DB_URL is not set in settings")
        LOGGER.error("Please set INGESTION_DB_URL in your environment or credentials.env file")
        return False

    try:
        LOGGER.info(f"Connecting to ingestion database...")
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
                    if not table_has_order_column(db_service, table, schema):
                        tables_to_migrate.append((schema, table))
                    else:
                        LOGGER.info(f"Skipping {schema}.{table} - already has '{ORDER_COLUMN_NAME}' column")

        if not tables_to_migrate:
            LOGGER.info(
                "No tables need migration. All tables either don't have 'chunk_id' or already have 'order' column."
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
            if add_order_column_to_table(db_service, table, schema):
                success_count += 1
                LOGGER.info(f"  ✓ Successfully migrated {schema}.{table}\n")
            else:
                failed_count += 1
                LOGGER.error(f"  ✗ Failed to migrate {schema}.{table}\n")

        # Summary
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
