"""reorganize_ingestion_tables_collections

Revision ID: 4786bbd3c51
Revises: f1e79aa97806
Create Date: 2025-01-20 12:00:00.000000

"""

from typing import Sequence, Union
import logging
import asyncio
import re

from sqlalchemy import text, create_engine
from alembic import op

from settings import settings

from data_ingestion.utils import sanitize_filename
from engine.qdrant_service import QdrantService
from engine.llm_services.llm_service import EmbeddingService
from engine.trace.trace_manager import TraceManager
from ada_backend.services.entity_factory import get_llm_provider_and_model
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
from ingestion_script.ingest_folder_source import TIMESTAMP_COLUMN_NAME, UNIFIED_QDRANT_SCHEMA

# revision identifiers, used by Alembic.
revision: str = "4786bbd3c51"
down_revision: Union[str, None] = "88dcf82ab86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Configure logger for migration - ensure it outputs to console
# The logger needs to have a handler and appropriate level to show logs during Alembic migration
LOGGER = logging.getLogger("alembic.migration")
LOGGER.setLevel(logging.INFO)

# Ensure the logger has a console handler
# Check if logger already has handlers (from alembic.ini config)
if not LOGGER.handlers:
    # Create console handler if none exists
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(levelname)-5.5s [%(name)s] %(message)s")
    console_handler.setFormatter(formatter)
    LOGGER.addHandler(console_handler)
    # Prevent propagation to root logger to avoid duplicate messages
    LOGGER.propagate = False
else:
    # If handlers exist, ensure level is set appropriately
    for handler in LOGGER.handlers:
        handler.setLevel(logging.INFO)

# Source ID to skip in migration (upgrade and downgrade)
TEST_SOURCE_ID = "ff39489a-ac21-4a5a-8ea6-e21f510b3538"


def _build_json_metadata_sql(metadata_cols, column_types=None):
    """Build PostgreSQL jsonb_build_object expression for JSON metadata.

    Args:
        metadata_cols: List of column names to include in metadata
        column_types: Optional dict mapping column names to their data types
    """
    if not metadata_cols:
        LOGGER.debug("No metadata columns to build JSON from")
        return "'{}'::jsonb"

    LOGGER.debug(f"Building JSON metadata from {len(metadata_cols)} columns: {metadata_cols}")

    # PostgreSQL: jsonb_build_object(key1, value1, key2, value2, ...)
    obj_parts = []
    for col in metadata_cols:
        col_type = column_types.get(col, "character varying") if column_types else "character varying"
        LOGGER.debug(f"Processing metadata column '{col}' with type '{col_type}'")

        # Handle different data types
        # jsonb_build_object automatically converts values to JSON, so we just need to handle NULLs
        if col_type in ("jsonb", "json"):
            # Already JSON, use as-is but ensure JSONB
            value_expr = f"COALESCE(\"{col}\"::jsonb, 'null'::jsonb)"
        elif col_type in ("boolean",):
            # Boolean - jsonb_build_object handles it correctly
            value_expr = f'"{col}"'
        elif col_type in ("integer", "bigint", "numeric", "double precision", "real"):
            # Numeric types - jsonb_build_object handles it correctly
            value_expr = f'"{col}"'
        else:
            # String types and others - jsonb_build_object converts to JSON string
            # Handle NULL by using empty string or null
            value_expr = f"COALESCE(\"{col}\"::text, '')"

        obj_parts.append(f"'{col}', {value_expr}")

    result = f"jsonb_build_object({', '.join(obj_parts)})"
    LOGGER.debug(f"Built JSON metadata expression: {result}")
    return result


def _migrate_table_with_sql_alternative(
    ingestion_db_connection, source_schema, source_table, target_schema, target_table, source_id, source_type
):
    """Alternative SQL-based migration using different approach."""
    # Get column info from source table (including data types)
    source_table_info = ingestion_db_connection.execute(
        text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = :schema_name
            AND table_name = :table_name
        """
        ),
        {"schema_name": source_schema, "table_name": source_table},
    ).fetchall()

    source_columns = [col[0] for col in source_table_info]
    column_types = {col[0]: col[1] for col in source_table_info}

    LOGGER.info(
        f"Alternative migration: Source table {source_schema}.{source_table} has {len(source_columns)} columns: {source_columns}"
    )

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
    has_existing_metadata = False
    existing_metadata_col = None

    for col in source_columns:
        col_lower = col.lower()
        if col_lower in common_columns:
            mapped_cols[col] = common_columns[col_lower]
        elif col == METADATA_COLUMN_NAME:
            has_existing_metadata = True
            existing_metadata_col = col
        elif col not in [SOURCE_ID_COLUMN_NAME, "processed_datetime"]:
            metadata_cols.append(col)

    LOGGER.info(
        f"Alternative migration column mapping for {source_schema}.{source_table}: "
        f"mapped={list(mapped_cols.keys())}, metadata={metadata_cols}, "
        f"has_existing_metadata={has_existing_metadata}"
    )

    # Build SELECT parts for mapped columns in the correct order
    # Order must match INSERT: chunk_id, source_id, source_identifier, content, url, last_edited_ts, source_metadata
    select_parts = []

    # Find which unified columns we have
    unified_cols_in_mapped = {unified_col: orig_col for orig_col, unified_col in mapped_cols.items()}

    # 1. chunk_id (first) - required
    if CHUNK_ID_COLUMN_NAME in unified_cols_in_mapped:
        orig_col = unified_cols_in_mapped[CHUNK_ID_COLUMN_NAME]
        if orig_col != CHUNK_ID_COLUMN_NAME:
            select_parts.append(f'"{orig_col}" AS "{CHUNK_ID_COLUMN_NAME}"')
        else:
            select_parts.append(f'"{CHUNK_ID_COLUMN_NAME}"')
    else:
        select_parts.append(f'NULL AS "{CHUNK_ID_COLUMN_NAME}"')

    # 2. source_id (second) - always added
    select_parts.append(f"'{source_id}' AS {SOURCE_ID_COLUMN_NAME}")

    # 3-6. Other mapped columns in order: source_identifier/file_id, content, url, last_edited_ts
    other_cols_order = [FILE_ID_COLUMN_NAME, CHUNK_COLUMN_NAME, URL_COLUMN_NAME, TIMESTAMP_COLUMN_NAME]
    for unified_col in other_cols_order:
        if unified_col in unified_cols_in_mapped:
            orig_col = unified_cols_in_mapped[unified_col]
            if orig_col != unified_col:
                select_parts.append(f'"{orig_col}" AS "{unified_col}"')
            else:
                select_parts.append(f'"{unified_col}"')
        else:
            select_parts.append(f'NULL AS "{unified_col}"')

    # 7. source_metadata (last)
    # Build JSON metadata expression (PostgreSQL) - ensure JSONB type
    new_metadata_expr = _build_json_metadata_sql(metadata_cols, column_types)

    # Merge with existing metadata if present, ensuring JSONB type
    if has_existing_metadata:
        # Cast existing metadata to JSONB and merge with new metadata
        # Use COALESCE to handle NULL values
        metadata_expr = f"COALESCE(\"{existing_metadata_col}\"::jsonb, '{{}}'::jsonb) || {new_metadata_expr}"
    else:
        metadata_expr = new_metadata_expr

    select_parts.append(f"{metadata_expr} AS {METADATA_COLUMN_NAME}")

    # Build and execute INSERT statement with ON CONFLICT to handle duplicates
    insert_sql = f"""
        INSERT INTO "{target_schema}"."{target_table}"
        ({CHUNK_ID_COLUMN_NAME}, {SOURCE_ID_COLUMN_NAME}, {FILE_ID_COLUMN_NAME}, {CHUNK_COLUMN_NAME}, {URL_COLUMN_NAME}, {TIMESTAMP_COLUMN_NAME}, {METADATA_COLUMN_NAME})
        SELECT {', '.join(select_parts)}
        FROM "{source_schema}"."{source_table}"
        ON CONFLICT ({CHUNK_ID_COLUMN_NAME}) DO NOTHING
    """

    LOGGER.debug(f"Alternative SQL INSERT for {source_schema}.{source_table}:\n{insert_sql}")

    try:
        result = ingestion_db_connection.execute(text(insert_sql))
        # Try to get rowcount if available
        try:
            rowcount = result.rowcount if hasattr(result, "rowcount") else None
            if rowcount is not None:
                LOGGER.info(
                    f"Successfully migrated {rowcount} rows from {source_schema}.{source_table} to {target_schema}.{target_table} using alternative SQL approach"
                )
            else:
                LOGGER.info(
                    f"Successfully migrated {source_schema}.{source_table} to {target_schema}.{target_table} using alternative SQL approach"
                )
        except:
            LOGGER.info(
                f"Successfully migrated {source_schema}.{source_table} to {target_schema}.{target_table} using alternative SQL approach"
            )
    except Exception as e:
        LOGGER.error(
            f"FAILED to migrate {source_schema}.{source_table} to {target_schema}.{target_table} using alternative SQL approach: {str(e)}\n"
            f"SQL: {insert_sql}"
        )
        raise


async def _merge_collections(
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
        LOGGER.warning(f"No source collections provided for organization {organization_id}, skipping collection merge")
        return False

    LOGGER.info(f"Merging {len(source_collections)} collections into {new_collection_name}")

    # Check if target collection already exists and has data
    if await qdrant_service.collection_exists_async(new_collection_name):
        point_count = await qdrant_service.count_points_async(new_collection_name)
        if point_count > 0:
            LOGGER.info(f"Collection {new_collection_name} already exists with {point_count} points, skipping merge")
            return False
        else:
            LOGGER.info(f"Collection {new_collection_name} exists but is empty, continuing migration")

    # Get collection config from first source collection
    first_collection_name = source_collections[0][1]
    if not await qdrant_service.collection_exists_async(first_collection_name):
        LOGGER.warning(f"Source collection {first_collection_name} does not exist, skipping")
        return False

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
                payload=scroll_payload,
            )

            if not scroll_response or "result" not in scroll_response:
                LOGGER.error(
                    f"Failed to scroll points from collection {collection_name} for source {source_id}. "
                    f"Response: {scroll_response}"
                )
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
        LOGGER.info(f"Inserting {len(all_points)} points into collection {new_collection_name}")
        batch_size = 100
        inserted_count = 0
        for i in range(0, len(all_points), batch_size):
            batch = all_points[i : i + batch_size]
            try:
                await qdrant_service._send_request_async(
                    method="PUT",
                    endpoint=f"collections/{new_collection_name}/points",
                    payload={"points": batch},
                )
                inserted_count += len(batch)
            except Exception as e:
                LOGGER.error(
                    f"Error inserting batch {i//batch_size + 1} into collection {new_collection_name}: {str(e)}. "
                    f"Batch size: {len(batch)}"
                )
                raise
        LOGGER.info(f"Successfully migrated {inserted_count} points to {new_collection_name}")
    else:
        LOGGER.warning(
            f"No points to migrate to {new_collection_name} from {len(source_collections)} source collections. "
            f"This may indicate that all source collections were empty or did not exist."
        )

    # NOTE: Old collections are NOT deleted here to allow for rollback.
    # They will be deleted in a subsequent migration/PR after verifying the migration was successful.
    LOGGER.info(
        f"Migration completed for {new_collection_name}. "
        f"Old collections ({len(source_collections)} collections) are preserved for now and will be deleted in a subsequent PR."
    )

    # Return True if migration was performed
    return True


def _merge_tables(
    ingestion_db_connection,
    organization_id: str,
    source_tables: list[tuple[str, str, str, str]],  # [(source_id, schema_name, table_name, source_type), ...]
):
    """Merge multiple source tables from ingestion DB into one organization-level table in ingestion DB public schema.

    Returns:
        bool: True if migration was performed (data was migrated), False if skipped (table already exists with data)
    """
    if not source_tables:
        return False

    sanitized_org_id = sanitize_filename(organization_id)
    new_table_name = f"org_{sanitized_org_id}"
    schema_name = "public"  # Use public schema for all tables

    if not source_tables:
        LOGGER.warning(f"No source tables provided for organization {organization_id}, skipping table merge")
        return False

    LOGGER.info(f"Merging {len(source_tables)} tables into {schema_name}.{new_table_name} in ingestion DB")

    # Check if target table already exists and has data
    # Use proper parameterized query (not f-string for WHERE clause)
    table_exists = ingestion_db_connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = :schema_name 
                AND table_name = :table_name
            )
        """
        ),
        {"schema_name": schema_name, "table_name": new_table_name},
    ).scalar()

    LOGGER.info(f"Checking table existence: schema={schema_name}, table={new_table_name}, exists={table_exists}")

    # Debug: Check if table exists in any schema
    if not table_exists:
        all_tables = ingestion_db_connection.execute(
            text(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables 
                WHERE table_name = :table_name
            """
            ),
            {"table_name": new_table_name},
        ).fetchall()
        if all_tables:
            LOGGER.warning(f"Table {new_table_name} exists in other schemas: {all_tables}")

    if table_exists:
        # Check if table has data
        row_count = ingestion_db_connection.execute(
            text(
                f"""
                SELECT COUNT(*) FROM "{schema_name}"."{new_table_name}"
            """
            ),
        ).scalar()

        if row_count > 0:
            LOGGER.info(f"Table {schema_name}.{new_table_name} already exists with {row_count} rows, skipping merge")
            return False
        else:
            LOGGER.info(f"Table {schema_name}.{new_table_name} exists but is empty, continuing migration")

    # Create unified table structure
    # Ensure public schema exists (it should by default, but we'll verify)
    # No need to create public schema as it exists by default

    # Create unified table with standard structure
    LOGGER.info(f"=== CREATING TABLE: {schema_name}.{new_table_name} ===")
    LOGGER.info(f"Full table path: {schema_name}.{new_table_name}")
    create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS "{schema_name}"."{new_table_name}" (
            "processed_datetime" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            "{CHUNK_ID_COLUMN_NAME}" VARCHAR NOT NULL PRIMARY KEY,
            "{SOURCE_ID_COLUMN_NAME}" UUID,
            "{FILE_ID_COLUMN_NAME}" VARCHAR,
            "{CHUNK_COLUMN_NAME}" VARCHAR,
            "{URL_COLUMN_NAME}" VARCHAR,
            "{TIMESTAMP_COLUMN_NAME}" VARCHAR,
            "{METADATA_COLUMN_NAME}" JSONB
        )
    """
    ingestion_db_connection.execute(text(create_table_sql))
    ingestion_db_connection.commit()

    # Verify table was created
    table_created = ingestion_db_connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = :schema_name 
                AND table_name = :table_name
            )
        """
        ),
        {"schema_name": schema_name, "table_name": new_table_name},
    ).scalar()

    if table_created:
        LOGGER.info(f"✓ Table {schema_name}.{new_table_name} successfully created/verified in ingestion database")
    else:
        LOGGER.error(f"✗ ERROR: Table {schema_name}.{new_table_name} was NOT created!")

    # Copy data from source tables to new table, transforming to unified structure
    for source_id, schema, table_name, source_type in source_tables:
        # Skip test sources
        if schema and "test" in schema.lower():
            LOGGER.info(f"Skipping test source: {schema}.{table_name} (source_id: {source_id})")
            continue
        if table_name and "test" in table_name.lower():
            LOGGER.info(f"Skipping test source: {schema}.{table_name} (source_id: {source_id})")
            continue

        # Check if source table exists in ingestion DB
        table_exists = ingestion_db_connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = :schema_name 
                    AND table_name = :table_name
                )
            """
            ),
            {"schema_name": schema, "table_name": table_name},
        ).scalar()

        if not table_exists:
            LOGGER.warning(
                f"Source table {schema}.{table_name} does not exist, skipping migration for source {source_id}"
            )
            continue

        # Get column info from source table in ingestion DB (including data types)
        source_table_info = ingestion_db_connection.execute(
            text(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = :schema_name
                AND table_name = :table_name
            """
            ),
            {"schema_name": schema, "table_name": table_name},
        ).fetchall()

        source_columns = [col[0] for col in source_table_info]
        column_types = {col[0]: col[1] for col in source_table_info}

        LOGGER.info(f"Source table {schema}.{table_name} has {len(source_columns)} columns: {source_columns}")

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
        has_existing_metadata = False
        existing_metadata_col = None

        for col in source_columns:
            col_lower = col.lower()
            if col_lower in common_columns:
                mapped_cols[col] = common_columns[col_lower]
            elif col == METADATA_COLUMN_NAME:
                has_existing_metadata = True
                existing_metadata_col = col
            elif col not in [SOURCE_ID_COLUMN_NAME, "processed_datetime"]:
                metadata_cols.append(col)

        LOGGER.info(
            f"Column mapping for {schema}.{table_name}: "
            f"mapped={list(mapped_cols.keys())}, metadata={metadata_cols}, "
            f"has_existing_metadata={has_existing_metadata}"
        )

        # Build SELECT parts for mapped columns in the correct order
        # Order must match INSERT: chunk_id, source_id, source_identifier, content, url, last_edited_ts, source_metadata
        select_parts = []

        # Find which unified columns we have
        unified_cols_in_mapped = {unified_col: orig_col for orig_col, unified_col in mapped_cols.items()}

        # 1. chunk_id (first) - required
        if CHUNK_ID_COLUMN_NAME in unified_cols_in_mapped:
            orig_col = unified_cols_in_mapped[CHUNK_ID_COLUMN_NAME]
            if orig_col != CHUNK_ID_COLUMN_NAME:
                select_parts.append(f'"{orig_col}" AS "{CHUNK_ID_COLUMN_NAME}"')
            else:
                select_parts.append(f'"{CHUNK_ID_COLUMN_NAME}"')
        else:
            select_parts.append(f'NULL AS "{CHUNK_ID_COLUMN_NAME}"')

        # 2. source_id (second) - always added (cast to UUID)
        select_parts.append(f"'{source_id}'::uuid AS {SOURCE_ID_COLUMN_NAME}")

        # 3-6. Other mapped columns in order: source_identifier/file_id, content, url, last_edited_ts
        other_cols_order = [FILE_ID_COLUMN_NAME, CHUNK_COLUMN_NAME, URL_COLUMN_NAME, TIMESTAMP_COLUMN_NAME]
        for unified_col in other_cols_order:
            if unified_col in unified_cols_in_mapped:
                orig_col = unified_cols_in_mapped[unified_col]
                if orig_col != unified_col:
                    select_parts.append(f'"{orig_col}" AS "{unified_col}"')
                else:
                    select_parts.append(f'"{unified_col}"')
            else:
                select_parts.append(f'NULL AS "{unified_col}"')

        # 7. source_metadata (last)
        # Build JSON metadata expression (PostgreSQL) - ensure JSONB type
        new_metadata_expr = _build_json_metadata_sql(metadata_cols, column_types)

        # Merge with existing metadata if present, ensuring JSONB type
        if has_existing_metadata:
            # Cast existing metadata to JSONB and merge with new metadata
            # Use COALESCE to handle NULL values
            metadata_expr = f"COALESCE(\"{existing_metadata_col}\"::jsonb, '{{}}'::jsonb) || {new_metadata_expr}"
        else:
            metadata_expr = new_metadata_expr

        select_parts.append(f"{metadata_expr} AS {METADATA_COLUMN_NAME}")

        # Build and execute INSERT statement with ON CONFLICT to handle duplicates
        insert_sql = f"""
            INSERT INTO "{schema_name}"."{new_table_name}"
            ({CHUNK_ID_COLUMN_NAME}, {SOURCE_ID_COLUMN_NAME}, {FILE_ID_COLUMN_NAME}, {CHUNK_COLUMN_NAME}, {URL_COLUMN_NAME}, {TIMESTAMP_COLUMN_NAME}, {METADATA_COLUMN_NAME})
            SELECT {', '.join(select_parts)}
            FROM "{schema}"."{table_name}"
            ON CONFLICT ({CHUNK_ID_COLUMN_NAME}) DO NOTHING
        """

        LOGGER.debug(f"SQL INSERT for {schema}.{table_name}:\n{insert_sql}")

        try:
            result = ingestion_db_connection.execute(text(insert_sql))
            # Try to get rowcount if available
            try:
                rowcount = result.rowcount if hasattr(result, "rowcount") else None
                if rowcount is not None:
                    LOGGER.info(
                        f"Successfully copied {rowcount} rows from {schema}.{table_name} to {schema_name}.{new_table_name}"
                    )
                else:
                    LOGGER.info(
                        f"Successfully copied data from {schema}.{table_name} to {schema_name}.{new_table_name}"
                    )
            except:
                LOGGER.info(f"Successfully copied data from {schema}.{table_name} to {schema_name}.{new_table_name}")
        except Exception as e:
            LOGGER.error(
                f"Error copying data from {schema}.{table_name} to {schema_name}.{new_table_name}: {str(e)}\n"
                f"SQL: {insert_sql}"
            )
            # Try alternative SQL approach with different JSON construction
            LOGGER.info(f"Attempting alternative SQL-based transformation for {schema}.{table_name}")
            try:
                _migrate_table_with_sql_alternative(
                    ingestion_db_connection, schema, table_name, schema_name, new_table_name, source_id, source_type
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

    # Return True if migration was performed (table was created and/or data was migrated)
    return True


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
    # Connection to principal database (for reading data_sources and updating it)
    principal_db_connection = op.get_bind()

    # Connection to ingestion database (for reading and writing ingestion tables)
    if not settings.INGESTION_DB_URL:
        LOGGER.error("INGESTION_DB_URL is not set. No migration to do. Skipping.")
        return

    LOGGER.info(f"=== MIGRATION START: Connecting to ingestion database ===")
    LOGGER.info(f"Ingestion database URL: {settings.INGESTION_DB_URL}")
    # Extract database name from URL for logging
    try:
        from urllib.parse import urlparse

        parsed_url = urlparse(settings.INGESTION_DB_URL)
        db_name = parsed_url.path.lstrip("/") if parsed_url.path else "unknown"
        LOGGER.info(f"Database name: {db_name}")
    except:
        pass

    try:
        ingestion_db_engine = create_engine(settings.INGESTION_DB_URL)
        ingestion_db_connection = ingestion_db_engine.connect()
        LOGGER.info(f"Successfully connected to ingestion database")

        # Get ALL sources with embedding model reference from principal database
        result = principal_db_connection.execute(
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
        for (
            source_id,
            org_id,
            db_schema,
            db_table,
            name,
            qdrant_collection,
            source_type,
            embedding_model,
        ) in all_sources:
            # Skip specific source_id
            if str(source_id) == TEST_SOURCE_ID:
                LOGGER.info(f"Skipping source {source_id} (excluded from migration)")
                continue

            # Use default embedding model if not provided
            model_ref = embedding_model or DEFAULT_EMBEDDING_MODEL
            key = (org_id, model_ref)
            if key not in org_model_sources:
                org_model_sources[key] = []
            org_model_sources[key].append(
                (source_id, db_schema, db_table, qdrant_collection, name, source_type, model_ref)
            )

            # Create a single TraceManager for the entire migration
            trace_manager = TraceManager(project_name="migration")

            # Create QdrantService for each unique embedding model
            # Each embedding model needs its own QdrantService instance
            qdrant_services = {}
            unique_embedding_models = set()
            for (org_id, embedding_model), sources in org_model_sources.items():
                unique_embedding_models.add(embedding_model)

            for embedding_model in unique_embedding_models:
                try:
                    provider, model_name = get_llm_provider_and_model(embedding_model)
                    embedding_service = EmbeddingService(
                        provider=provider,
                        model_name=model_name,
                        trace_manager=trace_manager,
                    )
                    qdrant_service = QdrantService.from_defaults(
                        embedding_service=embedding_service,
                        default_collection_schema=UNIFIED_QDRANT_SCHEMA,
                    )
                    qdrant_services[embedding_model] = qdrant_service
                    LOGGER.info(f"Created QdrantService for embedding model: {embedding_model}")
                except Exception as e:
                    LOGGER.error(f"Failed to create QdrantService for embedding model {embedding_model}: {str(e)}")
                    raise

            # Process each organization+embedding_model combination
            # Track migration statistics
            orgs_with_table_migrations = 0
            orgs_with_collection_migrations = 0
            orgs_skipped = 0

            for (org_id, embedding_model), sources in org_model_sources.items():
                LOGGER.info(
                    f"Processing organization {org_id} with embedding model {embedding_model} - {len(sources)} sources"
                )

                # Prepare data for merging
                source_tables = []
                source_collections = []

                for source_id, db_schema, db_table, qdrant_collection, name, source_type, emb_model in sources:
                    # Skip specific source_id
                    if str(source_id) == TEST_SOURCE_ID:
                        continue

                    if db_table:
                        source_tables.append((str(source_id), db_schema, db_table, source_type))
                    if qdrant_collection:
                        source_collections.append((str(source_id), qdrant_collection))

                # Merge tables in ingestion DB (tables are shared across all models in an org)
                tables_migrated = False
                if source_tables:
                    tables_migrated = _merge_tables(ingestion_db_connection, str(org_id), source_tables)
                    if tables_migrated:
                        orgs_with_table_migrations += 1
                else:
                    LOGGER.warning(f"No source tables found for organization {org_id}, skipping table migration")

                # Merge collections (collections are per org+model)
                # NOTE: Old collections are NOT deleted here - will be done in a subsequent PR
                # Use the QdrantService for this specific embedding model
                collections_migrated = False
                if source_collections:
                    qdrant_service = qdrant_services[embedding_model]
                    collections_migrated = asyncio.run(
                        _merge_collections(qdrant_service, str(org_id), source_collections, embedding_model)
                    )
                    if collections_migrated:
                        orgs_with_collection_migrations += 1
                else:
                    LOGGER.warning(
                        f"No source collections found for organization {org_id}, skipping collection migration"
                    )

                # Update data_sources table ONLY if migration was actually performed
                if tables_migrated or collections_migrated:
                    # Use get_sanitize_names to get the correct names based on org and embedding model
                    new_schema_name, new_table_name, new_collection_name = get_sanitize_names(
                        organization_id=str(org_id),
                        embedding_model_reference=embedding_model,
                    )

                    for source_id, db_schema, db_table, qdrant_collection, name, source_type, emb_model in sources:
                        # Skip specific source_id
                        if str(source_id) == TEST_SOURCE_ID:
                            continue

                        principal_db_connection.execute(
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
                else:
                    orgs_skipped += 1
                    LOGGER.info(
                        f"Skipping data_sources update for organization {org_id} - migration was skipped (tables/collections already exist with data)"
                    )

            # NOTE: Old tables and collections are NOT deleted in this migration.
            # They are preserved to allow for rollback and will be deleted in a subsequent PR.
            # After this migration, all new ingestions will use the new unified structures
            # (via the updated data_sources table), so no new data will be written to old structures.
            #
            # TODO (Next PR): Create a migration to delete old tables and collections:
            # - Old tables: tables in org_* schemas (not public) or tables named source_* in public schema
            # - Old collections: collections that don't match the new naming pattern org_{org_id}_{model}_collection
            # - Only delete after verifying migration was successful and no rollback is needed

            # Log migration summary
            total_orgs_processed = len(org_model_sources)
            if total_orgs_processed == 0:
                LOGGER.warning(
                    "Migration completed but NO organizations were processed. "
                    "This may indicate that no sources were found in data_sources table or all sources were skipped."
                )
            else:
                LOGGER.info(
                    f"Migration Step 1/2 completed: "
                    f"Processed {total_orgs_processed} organization(s), "
                    f"migrated tables for {orgs_with_table_migrations} organization(s), "
                    f"migrated collections for {orgs_with_collection_migrations} organization(s), "
                    f"skipped {orgs_skipped} organization(s) (already migrated). "
                    "Old structures preserved for rollback. They will be deleted in a subsequent PR."
                )

                # List all tables created in public schema of ingestion database
                LOGGER.info("=== VERIFICATION: Listing all tables in public schema of ingestion database ===")
                try:
                    all_tables = ingestion_db_connection.execute(
                        text(
                            """
                            SELECT table_name, 
                                   (SELECT COUNT(*) FROM information_schema.columns 
                                    WHERE table_schema = 'public' AND table_name = t.table_name) as column_count
                            FROM information_schema.tables t
                            WHERE table_schema = 'public'
                            AND table_name LIKE 'org_%'
                            ORDER BY table_name
                        """
                        )
                    ).fetchall()

                    if all_tables:
                        LOGGER.info(f"Found {len(all_tables)} table(s) in public schema matching pattern 'org_%':")
                        for table_name, col_count in all_tables:
                            # Get row count
                            try:
                                row_count = ingestion_db_connection.execute(
                                    text(f'SELECT COUNT(*) FROM "public"."{table_name}"')
                                ).scalar()
                                LOGGER.info(f"  - public.{table_name}: {col_count} columns, {row_count} rows")
                            except Exception as e:
                                LOGGER.warning(
                                    f"  - public.{table_name}: {col_count} columns (could not count rows: {e})"
                                )
                    else:
                        LOGGER.warning("No tables found in public schema matching pattern 'org_%'")
                except Exception as e:
                    LOGGER.error(f"Error listing tables: {e}")

                LOGGER.info("=== MIGRATION END ===")
    finally:
        # Close ingestion database connection
        ingestion_db_connection.close()
        ingestion_db_engine.dispose()


def downgrade() -> None:
    """
    Downgrade migration: Revert data_sources to point back to old per-source tables/collections.
    Note: We don't delete the merged tables/collections, we just revert the references.
    """
    # Connection to principal database
    principal_db_connection = op.get_bind()

    # Get all sources that were migrated (pointing to new unified structures)
    result = principal_db_connection.execute(
        text(
            """
            SELECT id, organization_id, database_schema, database_table_name, name, qdrant_collection_name, type, embedding_model_reference
            FROM data_sources
            WHERE database_schema = 'public'
            AND database_table_name LIKE 'org_%'
            ORDER BY organization_id
        """
        )
    )

    all_sources = result.fetchall()

    if not all_sources:
        LOGGER.info("No sources found to downgrade")
        return

    LOGGER.info(f"Reverting {len(all_sources)} sources to old table/collection structure")

    # Revert each source to point to old per-source tables/collections
    for (
        source_id,
        org_id,
        db_schema,
        db_table,
        name,
        qdrant_collection,
        source_type,
        embedding_model,
    ) in all_sources:
        # Skip specific source_id
        if str(source_id) == TEST_SOURCE_ID:
            LOGGER.info(f"Skipping source {source_id} in downgrade (excluded from migration)")
            continue

        # Reconstruct old schema and table names
        sanitized_org_id = sanitize_filename(str(org_id))
        old_schema = f"org_{sanitized_org_id}"
        sanitized_source_id = sanitize_filename(str(source_id))
        old_table_name = f"source_{sanitized_source_id}"

        # Reconstruct old collection name
        # Old collections were named: {source_id}_collection (from previous migration f1e79aa97806)
        old_collection_name = f"{sanitized_source_id}_collection"

        principal_db_connection.execute(
            text(
                """
                UPDATE data_sources
                SET database_schema = :old_schema,
                    database_table_name = :old_table_name,
                    qdrant_collection_name = :old_collection_name
                WHERE id = :source_id
            """
            ),
            {
                "old_schema": old_schema,
                "old_table_name": old_table_name,
                "old_collection_name": old_collection_name,
                "source_id": source_id,
            },
        )

        LOGGER.info(
            f"Reverted source {source_id} to {old_schema}.{old_table_name} and collection {old_collection_name}"
        )

    LOGGER.info(
        "Downgrade completed: data_sources reverted to point to old per-source tables. "
        "Note: Merged tables/collections in public schema are NOT deleted and remain available."
    )
