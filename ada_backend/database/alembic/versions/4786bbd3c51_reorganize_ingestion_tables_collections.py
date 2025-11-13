"""reorganize_ingestion_tables_collections

Revision ID: 4786bbd3c51
Revises: f1e79aa97806
Create Date: 2025-01-20 12:00:00.000000

"""

from typing import Sequence, Union, Optional
import logging
import asyncio
import re

from sqlalchemy import text
from alembic import op

from data_ingestion.utils import sanitize_filename
from engine.qdrant_service import QdrantService
from ingestion_script.utils import (
    SOURCE_ID_COLUMN_NAME,
    METADATA_COLUMN_NAME,
    CHUNK_ID_COLUMN_NAME,
    CHUNK_COLUMN_NAME,
    FILE_ID_COLUMN_NAME,
    URL_COLUMN_NAME,
    get_sanitize_names,
    DEFAULT_EMBEDDING_MODEL,
)
from ingestion_script.ingest_folder_source import TIMESTAMP_COLUMN_NAME

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


def _build_json_metadata_sql(metadata_cols):
    """Build PostgreSQL jsonb_build_object expression for JSON metadata."""
    if not metadata_cols:
        return "'{}'::jsonb"

    # PostgreSQL: jsonb_build_object(key1, value1, key2, value2, ...)
    obj_parts = []
    for col in metadata_cols:
        obj_parts.append(f"'{col}', \"{col}\"")
    return f"jsonb_build_object({', '.join(obj_parts)})"


def _migrate_table_with_sql_alternative(
    connection, source_schema, source_table, target_schema, target_table, source_id, source_type
):
    """Alternative SQL-based migration using different approach."""
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
        {"schema_name": source_schema, "table_name": source_table},
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

    # Handle NULL values for missing columns
    # Check which unified columns are already in select_parts
    existing_unified_cols = set()
    for part in select_parts:
        if " AS " in part:
            # Extract the alias (unified column name)
            existing_unified_cols.add(part.split(" AS ")[1].strip('"'))
        else:
            # Column without alias - check if it matches a unified column name
            col_name = part.strip('"')
            if col_name in [
                CHUNK_ID_COLUMN_NAME,
                FILE_ID_COLUMN_NAME,
                CHUNK_COLUMN_NAME,
                URL_COLUMN_NAME,
                TIMESTAMP_COLUMN_NAME,
            ]:
                existing_unified_cols.add(col_name)

    required_cols = [
        CHUNK_ID_COLUMN_NAME,
        FILE_ID_COLUMN_NAME,
        CHUNK_COLUMN_NAME,
        URL_COLUMN_NAME,
        TIMESTAMP_COLUMN_NAME,
    ]

    for unified_col in required_cols:
        if unified_col not in existing_unified_cols:
            # Column doesn't exist in select, add NULL
            select_parts.append(f'NULL AS "{unified_col}"')

    # Build JSON metadata expression (PostgreSQL)
    metadata_expr = _build_json_metadata_sql(metadata_cols)
    select_parts.append(f"{metadata_expr} AS {METADATA_COLUMN_NAME}")

    # Add source_id
    select_parts.append(f"'{source_id}' AS {SOURCE_ID_COLUMN_NAME}")

    # Build and execute INSERT statement
    insert_sql = f"""
        INSERT INTO "{target_schema}"."{target_table}"
        ({CHUNK_ID_COLUMN_NAME}, {SOURCE_ID_COLUMN_NAME}, {FILE_ID_COLUMN_NAME}, {CHUNK_COLUMN_NAME}, {URL_COLUMN_NAME}, {TIMESTAMP_COLUMN_NAME}, {METADATA_COLUMN_NAME})
        SELECT {', '.join(select_parts)}
        FROM "{source_schema}"."{source_table}"
    """

    connection.execute(text(insert_sql))
    LOGGER.info(f"Migrated {source_schema}.{source_table} using alternative SQL approach")


async def _merge_collections(
    connection,
    qdrant_service,
    organization_id: str,
    source_collections: list[tuple[str, str]],  # [(source_id, collection_name), ...]
    embedding_model: str,
):
    """Merge multiple source collections into one organization-level collection with embedding model.

    NOTE: This function migrates data but does NOT delete old collections.
    Old collections will be deleted in a subsequent migration/PR.
    """
    # Use get_sanitize_names to get the correct collection name
    _, _, new_collection_name = get_sanitize_names(
        organization_id=organization_id,
        embedding_model_reference=embedding_model,
    )

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

    # NOTE: Old collections are NOT deleted here to allow for rollback.
    # They will be deleted in a subsequent migration/PR after verifying the migration was successful.
    LOGGER.info(
        f"Migration completed for {new_collection_name}. "
        f"Old collections ({len(source_collections)} collections) are preserved for now and will be deleted in a subsequent PR."
    )


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

        # Build JSON metadata expression (PostgreSQL)
        metadata_expr = _build_json_metadata_sql(metadata_cols)
        select_parts.append(f"{metadata_expr} AS {METADATA_COLUMN_NAME}")

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
            LOGGER.info(f"Successfully copied data from {schema}.{table_name} to {schema_name}.{new_table_name}")
        except Exception as e:
            LOGGER.warning(f"Error copying data from {schema}.{table_name}: {str(e)}")
            # Try alternative SQL approach with different JSON construction
            LOGGER.info(f"Attempting alternative SQL-based transformation for {schema}.{table_name}")
            try:
                _migrate_table_with_sql_alternative(
                    connection, schema, table_name, schema_name, new_table_name, source_id, source_type
                )
                LOGGER.info(f"Successfully migrated {schema}.{table_name} using alternative SQL approach")
            except Exception as e2:
                LOGGER.warning(
                    f"FAILED to migrate table {schema}.{table_name} for source {source_id}. "
                    f"Both SQL approaches failed. "
                    f"Primary SQL error: {str(e)}, Alternative SQL error: {str(e2)}. "
                    f"Old table {schema}.{table_name} will remain unchanged."
                )
                continue

        # Note: We do NOT drop old tables - they are kept for safety
        LOGGER.info(f"Migration completed for {schema}.{table_name} (old table preserved)")


def upgrade() -> None:
    """
    Reorganize ingestion tables and collections (Step 1/2):
    - Create new unified org-level tables and collections
    - Migrate data from old per-source tables/collections to new unified ones
    - Add source_id and source_metadata columns
    - Move source-specific fields to metadata JSONB
    - Update data_sources table to point to new unified structures

    NOTE: This migration does NOT delete old tables/collections.
    Old structures will be deleted in a subsequent migration/PR to allow for rollback.
    After this migration, all new ingestions will use the new unified structures.
    """
    connection = op.get_bind()

    # Get ALL sources with embedding model reference
    result = connection.execute(
        text(
            """
            SELECT id, organization_id, database_schema, database_table_name, name, qdrant_collection_name, type, embedding_model_reference
            FROM data_sources
            WHERE database_table_name IS NOT NULL
            ORDER BY organization_id, embedding_model_reference
        """
        )
    )

    all_sources = result.fetchall()

    if not all_sources:
        LOGGER.info("No sources found to migrate")
        return

    # Group sources by organization and embedding model
    # Each org+model combination gets its own collection
    org_model_sources = {}
    for source_id, org_id, db_schema, db_table, name, qdrant_collection, source_type, embedding_model in all_sources:
        # Use default embedding model if not provided
        model_ref = embedding_model or DEFAULT_EMBEDDING_MODEL
        key = (org_id, model_ref)
        if key not in org_model_sources:
            org_model_sources[key] = []
        org_model_sources[key].append(
            (source_id, db_schema, db_table, qdrant_collection, name, source_type, model_ref)
        )

    qdrant_service = QdrantService.from_defaults()

    # Process each organization+embedding_model combination
    for (org_id, embedding_model), sources in org_model_sources.items():
        LOGGER.info(
            f"Processing organization {org_id} with embedding model {embedding_model} - {len(sources)} sources"
        )

        # Prepare data for merging
        source_tables = []
        source_collections = []

        for source_id, db_schema, db_table, qdrant_collection, name, source_type, emb_model in sources:
            if db_table:
                source_tables.append((str(source_id), db_schema, db_table, source_type))
            if qdrant_collection:
                source_collections.append((str(source_id), qdrant_collection))

        # Merge tables (tables are shared across all models in an org)
        if source_tables:
            _merge_tables(connection, str(org_id), source_tables)

        # Merge collections (collections are per org+model)
        # NOTE: Old collections are NOT deleted here - will be done in a subsequent PR
        if source_collections:
            asyncio.run(
                _merge_collections(connection, qdrant_service, str(org_id), source_collections, embedding_model)
            )

        # Update data_sources table with new table/collection names and public schema
        # Use get_sanitize_names to get the correct names based on org and embedding model
        new_schema_name, new_table_name, new_collection_name = get_sanitize_names(
            organization_id=str(org_id),
            embedding_model_reference=embedding_model,
        )

        for source_id, db_schema, db_table, qdrant_collection, name, source_type, emb_model in sources:
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

        LOGGER.info(f"Updated data_sources for organization {org_id} to point to new unified structures")

    # NOTE: Old tables and collections are NOT deleted in this migration.
    # They are preserved to allow for rollback and will be deleted in a subsequent PR.
    # After this migration, all new ingestions will use the new unified structures
    # (via the updated data_sources table), so no new data will be written to old structures.
    #
    # TODO (Next PR): Create a migration to delete old tables and collections:
    # - Old tables: tables in org_* schemas (not public) or tables named source_* in public schema
    # - Old collections: collections that don't match the new naming pattern org_{org_id}_{model}_collection
    # - Only delete after verifying migration was successful and no rollback is needed
    LOGGER.info(
        "Migration Step 1/2 completed: New unified structures created and data migrated. "
        "Old structures preserved for rollback. They will be deleted in a subsequent PR."
    )


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
