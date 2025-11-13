"""reorganize_ingestion_tables_collections

Revision ID: 4786bbd3c51
Revises: f1e79aa97806
Create Date: 2025-01-20 12:00:00.000000

"""

from typing import Sequence, Union
import logging
import asyncio
import re

from sqlalchemy import text
from alembic import op

from data_ingestion.utils import sanitize_filename
from engine.qdrant_service import QdrantService
from settings import settings
from ingestion_script.utils import SOURCE_ID_COLUMN_NAME, METADATA_COLUMN_NAME
from ada_backend.database import models as db

# revision identifiers, used by Alembic.
revision: str = "4786bbd3c51"
down_revision: Union[str, None] = "f1e79aa97806"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOGGER = logging.getLogger(__name__)


def _extract_source_id_from_table_name(table_name: str) -> str:
    """Extract source_id from table name like 'source_{source_id}'."""
    match = re.match(r"source_(.+)", table_name)
    if match:
        return match.group(1)
    return None


def _migrate_table_with_python(
    connection, source_schema, source_table, target_schema, target_table, source_id, source_type
):
    """Fallback Python-based migration for complex transformations."""
    import pandas as pd
    from ingestion_script.utils import CHUNK_ID_COLUMN_NAME, CHUNK_COLUMN_NAME, FILE_ID_COLUMN_NAME, URL_COLUMN_NAME
    from ingestion_script.ingest_folder_source import TIMESTAMP_COLUMN_NAME

    # Read all data from source table
    df = pd.read_sql(f'SELECT * FROM "{source_schema}"."{source_table}"', connection)

    if df.empty:
        LOGGER.warning(f"Source table {source_schema}.{source_table} is empty")
        return

    # Transform to unified structure
    unified_df = pd.DataFrame()

    # Map common columns
    column_mapping = {
        "chunk_id": CHUNK_ID_COLUMN_NAME,
        "content": CHUNK_COLUMN_NAME,
        "file_id": FILE_ID_COLUMN_NAME,
        "source_identifier": FILE_ID_COLUMN_NAME,
        "url": URL_COLUMN_NAME,
        "last_edited_ts": TIMESTAMP_COLUMN_NAME,
    }

    for old_col, new_col in column_mapping.items():
        if old_col in df.columns:
            unified_df[new_col] = df[old_col]
        elif new_col not in unified_df.columns:
            unified_df[new_col] = None

    # Build metadata JSONB
    metadata_cols = [
        col
        for col in df.columns
        if col.lower() not in column_mapping
        and col not in [SOURCE_ID_COLUMN_NAME, METADATA_COLUMN_NAME, "processed_datetime"]
    ]

    if metadata_cols:
        unified_df[METADATA_COLUMN_NAME] = df[metadata_cols].apply(lambda row: json.dumps(row.to_dict()), axis=1)
    else:
        unified_df[METADATA_COLUMN_NAME] = "{}"

    # Add source_id
    unified_df[SOURCE_ID_COLUMN_NAME] = source_id

    # Insert into target table
    unified_df.to_sql(target_table, connection, schema=target_schema, if_exists="append", index=False, method="multi")

    LOGGER.info(f"Migrated {len(unified_df)} rows from {source_schema}.{source_table} using Python")


async def _merge_collections(
    connection,
    qdrant_service,
    organization_id: str,
    source_collections: list[tuple[str, str]],  # [(source_id, collection_name), ...]
):
    """Merge multiple source collections into one organization-level collection."""
    sanitized_org_id = sanitize_filename(organization_id)
    new_collection_name = f"org_{sanitized_org_id}_collection"

    if not source_collections:
        return

    LOGGER.info(f"Merging {len(source_collections)} collections into {new_collection_name}")

    # Check if target collection already exists
    if await qdrant_service.collection_exists_async(new_collection_name):
        LOGGER.warning(f"Collection {new_collection_name} already exists, skipping merge")
        return

    # Get collection config from first source collection
    first_collection_name = source_collections[0][1]
    if not await qdrant_service.collection_exists_async(first_collection_name):
        LOGGER.warning(f"Source collection {first_collection_name} does not exist, skipping")
        return

    collection_info = await qdrant_service._send_request_async(
        method="GET", endpoint=f"collections/{first_collection_name}"
    )

    if not collection_info or "result" not in collection_info:
        LOGGER.error(f"Could not get collection info for {first_collection_name}")
        return

    collection_config = collection_info["result"]["config"]
    vector_size = collection_config["params"]["vectors"]["size"]
    distance = collection_config["params"]["vectors"]["distance"]

    # Create new collection
    await qdrant_service.create_collection_async(new_collection_name, vector_size=vector_size, distance=distance)

    # Copy all points from source collections to new collection, adding source_id
    all_points = []
    for source_id, collection_name in source_collections:
        if not await qdrant_service.collection_exists_async(collection_name):
            LOGGER.warning(f"Collection {collection_name} does not exist, skipping")
            continue

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

            scroll_response = await qdrant_service._send_request_async(
                method="POST",
                endpoint=f"collections/{collection_name}/points/scroll",
                json=scroll_payload,
            )

            if not scroll_response or "result" not in scroll_response:
                LOGGER.error(f"Failed to scroll points from collection {collection_name}")
                break

            result = scroll_response["result"]
            batch_points = result.get("points", [])

            if not batch_points:
                break

            # Add source_id to each point's payload
            for point in batch_points:
                if "payload" not in point:
                    point["payload"] = {}
                point["payload"][SOURCE_ID_COLUMN_NAME] = source_id

            all_points.extend(batch_points)
            offset = result.get("next_page_offset")

            if not offset:
                break

    # Insert all points into new collection
    if all_points:
        batch_size = 100
        for i in range(0, len(all_points), batch_size):
            batch = all_points[i : i + batch_size]
            await qdrant_service._send_request_async(
                method="PUT",
                endpoint=f"collections/{new_collection_name}/points",
                json={"points": batch},
            )
        LOGGER.info(f"Inserted {len(all_points)} points into {new_collection_name}")

    # Delete old collections
    for source_id, collection_name in source_collections:
        if await qdrant_service.collection_exists_async(collection_name):
            await qdrant_service.delete_collection_async(collection_name)
            LOGGER.info(f"Deleted old collection {collection_name}")


def _merge_tables(
    connection,
    organization_id: str,
    source_tables: list[tuple[str, str, str, str]],  # [(source_id, schema_name, table_name, source_type), ...]
):
    """Merge multiple source tables into one organization-level table."""
    if not source_tables:
        return

    sanitized_org_id = sanitize_filename(organization_id)
    new_table_name = f"org_{sanitized_org_id}_chunks"
    schema_name = "public"  # Use public schema for all tables

    LOGGER.info(f"Merging {len(source_tables)} tables into {schema_name}.{new_table_name}")

    # Check if target table already exists
    check_table = connection.execute(
        text(
            f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = :schema_name 
                AND table_name = :table_name
            )
        """
        ),
        {"schema_name": schema_name, "table_name": new_table_name},
    ).scalar()

    if check_table:
        LOGGER.warning(f"Table {schema_name}.{new_table_name} already exists, skipping merge")
        return

    # Create unified table structure
    # Common columns for all sources
    from ingestion_script.utils import CHUNK_ID_COLUMN_NAME, CHUNK_COLUMN_NAME, FILE_ID_COLUMN_NAME, URL_COLUMN_NAME
    from ingestion_script.ingest_folder_source import TIMESTAMP_COLUMN_NAME

    # Ensure public schema exists (it should by default, but we'll verify)
    # No need to create public schema as it exists by default

    # Create unified table with standard structure
    create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS "{schema_name}"."{new_table_name}" (
            "processed_datetime" DATETIME DEFAULT CURRENT_TIMESTAMP,
            "{CHUNK_ID_COLUMN_NAME}" VARCHAR NOT NULL PRIMARY KEY,
            "{SOURCE_ID_COLUMN_NAME}" VARCHAR,
            "{FILE_ID_COLUMN_NAME}" VARCHAR,
            "{CHUNK_COLUMN_NAME}" VARCHAR,
            "{URL_COLUMN_NAME}" VARCHAR,
            "{TIMESTAMP_COLUMN_NAME}" VARCHAR,
            "{METADATA_COLUMN_NAME}" VARIANT
        )
    """
    connection.execute(text(create_table_sql))

    # Copy data from source tables to new table, transforming to unified structure
    import json
    from ingestion_script.utils import CHUNK_ID_COLUMN_NAME, CHUNK_COLUMN_NAME, FILE_ID_COLUMN_NAME, URL_COLUMN_NAME
    from ingestion_script.ingest_folder_source import TIMESTAMP_COLUMN_NAME

    for source_id, schema, table_name, source_type in source_tables:
        # Get column info from source table
        source_table_info = connection.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = :schema_name
                AND table_name = :table_name
            """
            ),
            {"schema_name": schema, "table_name": table_name},
        ).fetchall()

        source_columns = [col[0] for col in source_table_info]

        # Define common columns that map directly
        common_columns = {
            "chunk_id": CHUNK_ID_COLUMN_NAME,
            "content": CHUNK_COLUMN_NAME,
            "file_id": FILE_ID_COLUMN_NAME,
            "source_identifier": FILE_ID_COLUMN_NAME,
            "url": URL_COLUMN_NAME,
            "last_edited_ts": TIMESTAMP_COLUMN_NAME,
        }

        # Build SELECT statement with column mapping
        # For now, we'll do a simpler migration: copy common columns and put everything else in metadata
        # This is a simplified approach - in production you might want more sophisticated transformation

        # Identify which columns to map directly
        mapped_cols = {}
        metadata_cols = []

        for col in source_columns:
            col_lower = col.lower()
            if col_lower in common_columns:
                mapped_cols[col] = common_columns[col_lower]
            elif col not in [SOURCE_ID_COLUMN_NAME, METADATA_COLUMN_NAME, "processed_datetime"]:
                metadata_cols.append(col)

        # Build SELECT parts for mapped columns
        select_parts = []
        for orig_col, unified_col in mapped_cols.items():
            if orig_col != unified_col:
                select_parts.append(f'"{orig_col}" AS "{unified_col}"')
            else:
                select_parts.append(f'"{orig_col}"')

        # Build OBJECT_CONSTRUCT for metadata (Snowflake syntax)
        # For other DBs, this might need adjustment
        if metadata_cols:
            obj_parts = []
            for col in metadata_cols:
                obj_parts.append(f"'{col}', \"{col}\"")
            select_parts.append(f"OBJECT_CONSTRUCT({', '.join(obj_parts)}) AS {METADATA_COLUMN_NAME}")
        else:
            select_parts.append(f"OBJECT_CONSTRUCT() AS {METADATA_COLUMN_NAME}")

        # Add source_id
        select_parts.append(f"'{source_id}' AS {SOURCE_ID_COLUMN_NAME}")

        # Build and execute INSERT statement
        insert_sql = f"""
            INSERT INTO "{schema_name}"."{new_table_name}"
            ({CHUNK_ID_COLUMN_NAME}, {SOURCE_ID_COLUMN_NAME}, {FILE_ID_COLUMN_NAME}, {CHUNK_COLUMN_NAME}, {URL_COLUMN_NAME}, {TIMESTAMP_COLUMN_NAME}, {METADATA_COLUMN_NAME})
            SELECT {', '.join(select_parts)}
            FROM "{schema}"."{table_name}"
        """

        try:
            connection.execute(text(insert_sql))
            LOGGER.info(f"Copied data from {schema}.{table_name} to {schema_name}.{new_table_name}")
        except Exception as e:
            LOGGER.error(f"Error copying data from {schema}.{table_name}: {str(e)}")
            # Try alternative approach with Python-based transformation if SQL fails
            LOGGER.info(f"Attempting Python-based transformation for {schema}.{table_name}")
            try:
                _migrate_table_with_python(
                    connection, schema, table_name, schema_name, new_table_name, source_id, source_type
                )
            except Exception as e2:
                LOGGER.error(f"Python-based migration also failed: {str(e2)}")
                continue

        # Drop old table
        connection.execute(text(f'DROP TABLE IF EXISTS "{schema}"."{table_name}"'))
        LOGGER.info(f"Dropped old table {schema}.{table_name}")


def upgrade() -> None:
    """
    Reorganize ingestion tables and collections:
    - Merge ALL sources into org-level tables and collections
    - Add source_id and source_metadata columns
    - Move source-specific fields to metadata JSONB
    - Update data_sources table with new names
    """
    connection = op.get_bind()

    # Get ALL sources
    result = connection.execute(
        text(
            """
            SELECT id, organization_id, database_schema, database_table_name, name, qdrant_collection_name, type
            FROM data_sources
            WHERE database_table_name IS NOT NULL
            ORDER BY organization_id
        """
        )
    )

    all_sources = result.fetchall()

    if not all_sources:
        LOGGER.info("No sources found to migrate")
        return

    # Group sources by organization
    org_sources = {}
    for source_id, org_id, db_schema, db_table, name, qdrant_collection, source_type in all_sources:
        if org_id not in org_sources:
            org_sources[org_id] = []
        org_sources[org_id].append((source_id, db_schema, db_table, qdrant_collection, name, source_type))

    qdrant_service = QdrantService.from_defaults()

    # Process each organization
    for org_id, sources in org_sources.items():
        LOGGER.info(f"Processing organization {org_id} with {len(sources)} sources")

        # Prepare data for merging
        source_tables = []
        source_collections = []

        for source_id, db_schema, db_table, qdrant_collection, name, source_type in sources:
            if db_table:
                source_tables.append((str(source_id), db_schema, db_table, source_type))
            if qdrant_collection:
                source_collections.append((str(source_id), qdrant_collection))

        # Merge tables
        if source_tables:
            _merge_tables(connection, str(org_id), source_tables)

        # Merge collections
        if source_collections:
            asyncio.run(_merge_collections(connection, qdrant_service, str(org_id), source_collections))

        # Update data_sources table with new table/collection names and public schema
        sanitized_org_id = sanitize_filename(str(org_id))
        new_table_name = f"org_{sanitized_org_id}_chunks"
        new_collection_name = f"org_{sanitized_org_id}_collection"
        new_schema_name = "public"

        for source_id, db_schema, db_table, qdrant_collection, name, source_type in sources:
            connection.execute(
                text(
                    """
                    UPDATE data_sources
                    SET database_schema = :new_schema_name,
                        database_table_name = :new_table_name,
                        qdrant_collection_name = :new_collection_name
                    WHERE id = :source_id
                """
                ),
                {
                    "new_schema_name": new_schema_name,
                    "new_table_name": new_table_name,
                    "new_collection_name": new_collection_name,
                    "source_id": source_id,
                },
            )

        LOGGER.info(f"Updated data_sources for organization {org_id}")


def downgrade() -> None:
    """
    Downgrade migration: This is complex and potentially data-lossy.
    We cannot easily split merged tables/collections back.
    For now, we'll just log a warning.
    """
    LOGGER.warning(
        "Downgrade not fully implemented. Merged tables/collections cannot be automatically split back. "
        "Manual intervention required."
    )
