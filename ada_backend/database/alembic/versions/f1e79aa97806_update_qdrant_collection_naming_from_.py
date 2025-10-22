"""update_qdrant_collection_naming_from_source_name_to_source_id

Revision ID: f1e79aa97806
Revises: 8ae8246c0768
Create Date: 2025-10-16 15:35:48.748785

"""

from typing import Sequence, Union
import logging
import asyncio

from sqlalchemy import text
from alembic import op

from data_ingestion.utils import sanitize_filename
from engine.qdrant_service import QdrantService
from settings import settings
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# revision identifiers, used by Alembic.
revision: str = "f1e79aa97806"
down_revision: Union[str, None] = "c4aa0d13832e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOGGER = logging.getLogger(__name__)


async def _process_collection(
    connection,
    qdrant_service,
    source_id,
    old_collection_name,
    new_collection_name,
    current_collection_name,
    operation_name,
):
    """
    Process a single Qdrant collection rename operation.

    Args:
        connection: Database connection
        qdrant_service: Qdrant service instance
        source_id: Source ID
        old_collection_name: Expected old collection name
        new_collection_name: Target new collection name
        current_collection_name: Current collection name in database
        operation_name: Name of the operation for logging ("rename" or "downgrade")
    """
    try:
        if current_collection_name != old_collection_name:
            if current_collection_name == new_collection_name:
                LOGGER.info(
                    f"Collection {current_collection_name} already in target format. Skipping {operation_name}."
                )
            else:
                LOGGER.warning(
                    f"Collection {current_collection_name} doesn't match expected format "
                    f"({old_collection_name}). Skipping to avoid data loss."
                )
            return False

        if await qdrant_service.collection_exists_async(new_collection_name):
            LOGGER.warning(
                f"Collection {new_collection_name} already exists. Skipping {operation_name} for source {source_id}"
            )
            return False

        if not await qdrant_service.collection_exists_async(current_collection_name):
            LOGGER.warning(f"Collection {current_collection_name} does not exist in Qdrant")
            return False

        collection_info = await qdrant_service._send_request_async(
            method="GET", endpoint=f"collections/{current_collection_name}"
        )

        if not collection_info or "result" not in collection_info:
            LOGGER.error(f"Could not get collection info for {current_collection_name}")
            return False

        collection_config = collection_info["result"]["config"]
        vector_size = collection_config["params"]["vectors"]["size"]
        distance = collection_config["params"]["vectors"]["distance"]

        await qdrant_service.create_collection_async(new_collection_name, vector_size=vector_size, distance=distance)

        all_points = []
        offset = None
        batch_size = 1000

        while True:
            scroll_payload = {
                "limit": batch_size,
                "with_payload": True,
                "with_vector": True,
            }
            if offset:
                scroll_payload["offset"] = offset

            scroll_result = await qdrant_service._send_request_async(
                method="POST",
                endpoint=f"collections/{current_collection_name}/points/scroll",
                payload=scroll_payload,
            )

            if not scroll_result or "result" not in scroll_result:
                LOGGER.error(f"Failed to scroll points from collection {current_collection_name}")
                break

            batch_points = scroll_result["result"]["points"]
            if not batch_points:
                break

            all_points.extend(batch_points)
            LOGGER.info(
                f"Retrieved {len(batch_points)} points from {current_collection_name} (total: {len(all_points)})"
            )

            if len(batch_points) < batch_size:
                break

            offset = batch_points[-1]["id"]

        if all_points:
            LOGGER.info(f"Inserting {len(all_points)} points into new collection {new_collection_name}")

            insert_batch_size = 100
            for i in range(0, len(all_points), insert_batch_size):
                batch = all_points[i : i + insert_batch_size]
                await qdrant_service._send_request_async(
                    method="PUT",
                    endpoint=f"collections/{new_collection_name}/points",
                    payload={"points": batch},
                )
                LOGGER.info(
                    f"Inserted batch {i//insert_batch_size + 1}/"
                    "{(len(all_points) + insert_batch_size - 1)//insert_batch_size}"
                )
        else:
            LOGGER.warning(f"No points found in collection {current_collection_name}")

        await qdrant_service.delete_collection_async(current_collection_name)

        connection.execute(
            text(
                """
            UPDATE data_sources
            SET qdrant_collection_name = :new_name
            WHERE id = :source_id
        """
            ),
            {"new_name": new_collection_name, "source_id": source_id},
        )

        LOGGER.info(
            f"Successfully {operation_name}d collection from {current_collection_name} to {new_collection_name}"
        )
        return True

    except Exception as e:
        LOGGER.error(f"Error {operation_name}ing collection for source {source_id}: {str(e)}")
        return False


async def upgrade_collections(connection, qdrant_service, data_sources):
    """
    Rename Qdrant collections from org_id_source_name format to source_id format.
    """
    renamed_count = 0
    skipped_count = 0

    for (
        source_id,
        organization_id,
        _,
        _,
        source_name,
        current_collection_name,
    ) in data_sources:
        if current_collection_name is None:
            LOGGER.info(f"Skipping collection for source {source_id} because it is not set")
            continue

        sanitized_organization_id = sanitize_filename(str(organization_id))
        sanitized_source_name = sanitize_filename(str(source_name))
        sanitized_source_id = sanitize_filename(str(source_id))

        old_collection_name = f"{sanitized_organization_id}_{sanitized_source_name}_collection"
        new_collection_name = f"{sanitized_source_id}_collection"

        success = await _process_collection(
            connection=connection,
            qdrant_service=qdrant_service,
            source_id=source_id,
            old_collection_name=old_collection_name,
            new_collection_name=new_collection_name,
            current_collection_name=current_collection_name,
            operation_name="upgrade",
        )

        if success:
            renamed_count += 1
        else:
            skipped_count += 1

    LOGGER.info(f"Successfully renamed {renamed_count} Qdrant collections, skipped {skipped_count} collections")


async def downgrade_collections(connection, qdrant_service, data_sources):
    """
    Downgrade Qdrant collections from source_id format back to org_id_source_name format.
    """
    renamed_count = 0
    skipped_count = 0

    for (
        source_id,
        organization_id,
        _,
        _,
        source_name,
        current_collection_name,
    ) in data_sources:
        if current_collection_name is None:
            LOGGER.info(f"Skipping collection for source {source_id} because it is not set")
            continue

        sanitized_organization_id = sanitize_filename(str(organization_id))
        sanitized_source_name = sanitize_filename(str(source_name))
        sanitized_source_id = sanitize_filename(str(source_id))

        old_collection_name = f"{sanitized_source_id}_collection"
        new_collection_name = f"{sanitized_organization_id}_{sanitized_source_name}_collection"

        success = await _process_collection(
            connection=connection,
            qdrant_service=qdrant_service,
            source_id=source_id,
            old_collection_name=old_collection_name,
            new_collection_name=new_collection_name,
            current_collection_name=current_collection_name,
            operation_name="downgrade",
        )

        if success:
            renamed_count += 1
        else:
            skipped_count += 1

    LOGGER.info(f"Successfully downgraded {renamed_count} Qdrant collections, skipped {skipped_count} collections")


def _process_table(connection, schema_name, old_table_name, new_table_name, source_id, operation_name):
    """
    Process a single table rename operation in the ingestion database.

    Args:
        schema_name: Database schema name (e.g., "org_123")
        old_table_name: Expected old table name
        new_table_name: Target new table name
        source_id: Source ID for logging
        operation_name: Name of the operation for logging ("rename" or "downgrade")

    Returns:
        bool: True if successful, False if skipped or error
    """
    if not settings.INGESTION_DB_URL:
        LOGGER.warning("INGESTION_DB_URL not set. Skipping ingestion database table operations.")
        return False

    try:
        ingestion_conn = psycopg2.connect(settings.INGESTION_DB_URL)
        ingestion_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        ingestion_cursor = ingestion_conn.cursor()

        # Check if schema exists
        ingestion_cursor.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s", (schema_name,)
        )
        if not ingestion_cursor.fetchone():
            LOGGER.warning(
                f"Schema {schema_name} does not exist. Skipping table {operation_name} for source {source_id}"
            )
            return False

        # Check if old table exists
        ingestion_cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema_name, old_table_name),
        )
        if not ingestion_cursor.fetchone():
            LOGGER.warning(f"Table {schema_name}.{old_table_name} does not exist. Skipping.")
            return False

        # Check if new table already exists
        ingestion_cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema_name, new_table_name),
        )
        if ingestion_cursor.fetchone():
            LOGGER.warning(f"Table {schema_name}.{new_table_name} already exists. Skipping {operation_name}.")
            return False

        # Rename the table
        rename_query = f'ALTER TABLE "{schema_name}"."{old_table_name}" RENAME TO "{new_table_name}"'
        ingestion_cursor.execute(rename_query)

        LOGGER.info(
            f"Successfully {operation_name}d table {schema_name}.{old_table_name} to {schema_name}.{new_table_name}"
        )
        connection.execute(
            text(
                """
            UPDATE data_sources
            SET database_table_name = :new_table_name
            WHERE id = :source_id
            """
            ),
            {"new_table_name": new_table_name, "source_id": source_id},
        )
        LOGGER.info(f"Successfully updated database table name for source {source_id} to {new_table_name}")
        return True

    except Exception as e:
        LOGGER.error(f"Error {operation_name}ing table for source {source_id}: {str(e)}")
        return False
    finally:
        if "ingestion_cursor" in locals():
            ingestion_cursor.close()
        if "ingestion_conn" in locals():
            ingestion_conn.close()


def upgrade_ingestion_db_tables(connection, data_sources):
    """
    Rename tables in the ingestion database from source_name_table to source_{source_id.
    """
    renamed_count = 0
    skipped_count = 0

    for (
        source_id,
        _,
        database_schema,
        database_table_name,
        _,
        _,
    ) in data_sources:
        schema_name = database_schema
        old_table_name = database_table_name
        sanitized_source_id = sanitize_filename(str(source_id))
        new_table_name = f"source_{sanitized_source_id}"

        success = _process_table(
            connection=connection,
            schema_name=schema_name,
            old_table_name=old_table_name,
            new_table_name=new_table_name,
            source_id=source_id,
            operation_name="upgrade",
        )

        if success:
            renamed_count += 1
        else:
            skipped_count += 1

    LOGGER.info(f"Successfully renamed {renamed_count} ingestion database tables, skipped {skipped_count} tables")


def downgrade_ingestion_db_tables(connection, data_sources):
    """
    Downgrade ingestion database tables from source_{source_id} back to source_name_table.
    """
    renamed_count = 0
    skipped_count = 0

    for (
        source_id,
        _,
        database_schema,
        database_table_name,
        source_name,
        _,
    ) in data_sources:
        sanitized_source_name = sanitize_filename(str(source_name))
        success = _process_table(
            connection=connection,
            schema_name=database_schema,
            old_table_name=database_table_name,
            new_table_name=f"{sanitized_source_name}_table",
            source_id=source_id,
            operation_name="downgrade",
        )

        if success:
            renamed_count += 1
        else:
            skipped_count += 1

    LOGGER.info(f"Successfully downgraded {renamed_count} ingestion database tables, skipped {skipped_count} tables")


def upgrade() -> None:
    """
    Rename Qdrant collections from org_id_source_name format to source_{source_id} format,
    rename ingestion database tables from source_name_table to source_{source_id},
    and update database_table_name and database_schema in data_sources using source_attributes information.
    This migration updates the qdrant_collection_name field in data_sources table,
    renames the actual collections in Qdrant, renames tables in the ingestion database,
    and updates database table names and schemas using information from source_attributes.
    """
    connection = op.get_bind()

    result = connection.execute(
        text(
            """
        SELECT id, organization_id, database_schema, database_table_name, name, qdrant_collection_name
        FROM data_sources
    """
        )
    )

    data_sources = result.fetchall()
    if not data_sources:
        LOGGER.info("No data sources found")
    else:
        qdrant_service = QdrantService.from_defaults()
        asyncio.run(upgrade_collections(connection, qdrant_service, data_sources))
        upgrade_ingestion_db_tables(connection, data_sources)


def downgrade() -> None:
    """
    Downgrade migration: rename Qdrant collections from source_{source_id} format back to org_id_source_name format,
    rename ingestion database tables from source_{source_id} back to source_name_table,
    and revert database_table_name and database_schema in data_sources.
    """
    connection = op.get_bind()

    result = connection.execute(
        text(
            """
        SELECT id, organization_id, database_schema, database_table_name, name, qdrant_collection_name
        FROM data_sources
    """
        )
    )

    data_sources = result.fetchall()

    if not data_sources:
        LOGGER.info("No data sources found")
    else:
        qdrant_service = QdrantService.from_defaults()
        asyncio.run(downgrade_collections(connection, qdrant_service, data_sources))
        downgrade_ingestion_db_tables(connection, data_sources)
