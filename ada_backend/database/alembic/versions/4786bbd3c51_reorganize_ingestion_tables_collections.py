"""reorganize_ingestion_tables_collections

Revision ID: 4786bbd3c51
Revises: 3f8319d78154
Create Date: 2025-01-20 12:00:00.000000

"""

import asyncio
import logging
from typing import Sequence, Union

from alembic import op
from sqlalchemy import MetaData, Table, create_engine, text

from ada_backend.services.entity_factory import get_llm_provider_and_model
from data_ingestion.utils import sanitize_filename
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import FieldSchema, QdrantService
from engine.storage_service.db_utils import PROCESSED_DATETIME_FIELD
from engine.storage_service.local_service import SQLLocalService
from engine.trace.trace_manager import TraceManager
from ingestion_script.ingest_folder_source import (
    TIMESTAMP_COLUMN_NAME,
    UNIFIED_QDRANT_SCHEMA,
    UNIFIED_TABLE_DEFINITION,
)
from ingestion_script.utils import (
    CHUNK_COLUMN_NAME,
    CHUNK_ID_COLUMN_NAME,
    DEFAULT_EMBEDDING_MODEL,
    DOCUMENT_TITLE_COLUMN_NAME,
    FILE_ID_COLUMN_NAME,
    METADATA_COLUMN_NAME,
    ORDER_COLUMN_NAME,
    SOURCE_ID_COLUMN_NAME,
    URL_COLUMN_NAME,
    get_sanitize_names,
)
from settings import settings

# revision identifiers, used by Alembic.
revision: str = "4786bbd3c51"
down_revision: Union[str, None] = "3f8319d78154"
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


def _create_table_from_definition(connection, table_definition, schema_name, table_name):
    """Create a table using DBDefinition, reusing SQLLocalService logic.

    Args:
        connection: SQLAlchemy connection object
        table_definition: DBDefinition object
        schema_name: Schema name for the table
        table_name: Table name
    """
    # Reuse the existing conversion function from SQLLocalService
    columns = SQLLocalService.convert_table_definition_to_sqlalchemy(table_definition)

    # Create SQLAlchemy Table object
    metadata = MetaData()
    table = Table(table_name, metadata, *columns, schema=schema_name)

    # Create the table using the connection (connection can be used as bind in SQLAlchemy)
    table.create(bind=connection, checkfirst=True)


def _check_table_exists(connection, schema_name, table_name):
    """Check if a table exists in the given schema.

    Returns:
        bool: True if table exists, False otherwise
    """
    try:
        exists = connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = :schema_name
                    AND table_name = :table_name
                )
            """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        ).scalar()
        return exists
    except Exception as e:
        LOGGER.error(f"Error checking if table exists: {e}")
        # Retry once in case of transient issues
        try:
            exists = connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = :schema_name
                        AND table_name = :table_name
                    )
                """
                ),
                {"schema_name": schema_name, "table_name": table_name},
            ).scalar()
            return exists
        except Exception as e2:
            LOGGER.error(f"Error on retry: {e2}")
            return False


def _ensure_composite_primary_key(connection, schema_name, table_name):
    """Ensure table has composite primary key on (chunk_id, source_id).

    If table has old single-column primary key on chunk_id, drop it and add composite key.
    If table has no primary key, add composite key.
    If table already has composite key, do nothing.
    """
    try:
        # Check current primary key constraint
        pk_info = connection.execute(
            text(
                """
                SELECT tc.constraint_name, string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position) as columns
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_schema = :schema_name
                    AND tc.table_name = :table_name
                GROUP BY tc.constraint_name
            """
            ),
            {"schema_name": schema_name, "table_name": table_name},
        ).fetchone()

        if pk_info:
            constraint_name, columns = pk_info
            columns_list = [col.strip().lower() for col in columns.split(",")]

            # Check if it's already the composite key
            has_chunk_id = CHUNK_ID_COLUMN_NAME.lower() in columns_list
            has_source_id = SOURCE_ID_COLUMN_NAME.lower() in columns_list

            if has_chunk_id and has_source_id and len(columns_list) == 2:
                LOGGER.info(
                    f"Table {schema_name}.{table_name} already has composite primary key "
                    f"on ({CHUNK_ID_COLUMN_NAME}, {SOURCE_ID_COLUMN_NAME})"
                )
                return True

            # Drop existing primary key (old single-column or incorrect composite)
            LOGGER.info(
                f"Dropping existing primary key constraint '{constraint_name}' "
                f"from {schema_name}.{table_name} (columns: {columns})"
            )
            connection.execute(text(f'ALTER TABLE "{schema_name}"."{table_name}" DROP CONSTRAINT "{constraint_name}"'))

        # Check for NULL values in chunk_id or source_id
        null_chunk_count = connection.execute(
            text(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}" WHERE "{CHUNK_ID_COLUMN_NAME}" IS NULL')
        ).scalar()

        null_source_count = connection.execute(
            text(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}" WHERE "{SOURCE_ID_COLUMN_NAME}" IS NULL')
        ).scalar()

        if null_chunk_count and null_chunk_count > 0:
            LOGGER.error(
                f"Cannot add composite primary key: {null_chunk_count} rows have NULL values "
                f"in {CHUNK_ID_COLUMN_NAME} for table {schema_name}.{table_name}"
            )
            return False

        if null_source_count and null_source_count > 0:
            LOGGER.error(
                f"Cannot add composite primary key: {null_source_count} rows have NULL values "
                f"in {SOURCE_ID_COLUMN_NAME} for table {schema_name}.{table_name}"
            )
            return False

        # Add composite primary key
        constraint_name = f"{table_name}_{CHUNK_ID_COLUMN_NAME}_{SOURCE_ID_COLUMN_NAME}_pk"
        connection.execute(
            text(
                f'ALTER TABLE "{schema_name}"."{table_name}" '
                f'ADD CONSTRAINT "{constraint_name}" '
                f'PRIMARY KEY ("{CHUNK_ID_COLUMN_NAME}", "{SOURCE_ID_COLUMN_NAME}")'
            )
        )
        LOGGER.info(
            f"Added composite primary key constraint on ({CHUNK_ID_COLUMN_NAME}, {SOURCE_ID_COLUMN_NAME}) "
            f"to table {schema_name}.{table_name}"
        )
        return True

    except Exception as e:
        LOGGER.error(f"Error ensuring composite primary key for {schema_name}.{table_name}: {str(e)}")
        import traceback

        LOGGER.error(traceback.format_exc())
        return False


def _get_table_column_info(connection, schema_name, table_name):
    """Get column information (name and data type) for a table.

    Returns:
        tuple: (source_columns, column_types) where:
            - source_columns: list of column names
            - column_types: dict mapping column names to their data types
    """
    source_table_info = connection.execute(
        text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = :schema_name
            AND table_name = :table_name
        """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    ).fetchall()

    source_columns = [col[0] for col in source_table_info]
    column_types = {col[0]: col[1] for col in source_table_info}
    return source_columns, column_types


def _build_select_parts_for_migration(source_id, mapped_cols, metadata_cols, column_types):
    """Build SELECT parts for INSERT statement in the correct order.

    Args:
        source_id: Source ID to use in the migration
        mapped_cols: Dict mapping source column names to unified column names
        metadata_cols: List of column names to put in metadata (including old "metadata" column)
        column_types: Dict mapping column names to their data types

    Returns:
        list: List of SELECT part strings in the correct order
    """
    select_parts = []

    # Find which unified columns we have
    unified_cols_in_mapped = {unified_col: orig_col for orig_col, unified_col in mapped_cols.items()}

    # 0. processed_datetime (first) - use CURRENT_TIMESTAMP as default
    select_parts.append(f'CURRENT_TIMESTAMP AS "{PROCESSED_DATETIME_FIELD}"')

    # 1. source_id - always added (cast to UUID)
    select_parts.append(f"'{source_id}'::uuid AS {SOURCE_ID_COLUMN_NAME}")

    # 2. chunk_id
    if CHUNK_ID_COLUMN_NAME in unified_cols_in_mapped:
        orig_col = unified_cols_in_mapped[CHUNK_ID_COLUMN_NAME]
        if orig_col != CHUNK_ID_COLUMN_NAME:
            select_parts.append(f'"{orig_col}" AS "{CHUNK_ID_COLUMN_NAME}"')
        else:
            select_parts.append(f'"{CHUNK_ID_COLUMN_NAME}"')
    else:
        select_parts.append(f'NULL AS "{CHUNK_ID_COLUMN_NAME}"')

    # 2.5. order
    if ORDER_COLUMN_NAME in unified_cols_in_mapped:
        orig_col = unified_cols_in_mapped[ORDER_COLUMN_NAME]
        if orig_col != ORDER_COLUMN_NAME:
            select_parts.append(f'"{orig_col}" AS "{ORDER_COLUMN_NAME}"')
        else:
            select_parts.append(f'"{ORDER_COLUMN_NAME}"')
    else:
        select_parts.append(f'NULL AS "{ORDER_COLUMN_NAME}"')

    # 3-5. Other mapped columns in order: file_id, document_title, url, content, timestamp
    other_cols_order = [
        FILE_ID_COLUMN_NAME,
        DOCUMENT_TITLE_COLUMN_NAME,
        URL_COLUMN_NAME,
        CHUNK_COLUMN_NAME,
        TIMESTAMP_COLUMN_NAME,
    ]
    for unified_col in other_cols_order:
        if unified_col in unified_cols_in_mapped:
            orig_col = unified_cols_in_mapped[unified_col]
            if orig_col != unified_col:
                select_parts.append(f'"{orig_col}" AS "{unified_col}"')
            else:
                select_parts.append(f'"{unified_col}"')
        else:
            select_parts.append(f'NULL AS "{unified_col}"')

    # 6. source_metadata (last)
    metadata_expr = _build_json_metadata_sql(metadata_cols, column_types)
    select_parts.append(f"{metadata_expr} AS {METADATA_COLUMN_NAME}")

    return select_parts


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


def _classify_columns(source_columns, column_types):
    """Classify source columns into normal columns and metadata columns.

    Returns:
        tuple: (mapped_cols, metadata_cols)
            - mapped_cols: dict {source_col_name: unified_col_name}
            - metadata_cols: list of column names to put in metadata
    """
    normal_columns_map = {
        CHUNK_ID_COLUMN_NAME.lower(): CHUNK_ID_COLUMN_NAME,
        CHUNK_COLUMN_NAME.lower(): CHUNK_COLUMN_NAME,
        FILE_ID_COLUMN_NAME.lower(): FILE_ID_COLUMN_NAME,
        "file_id": FILE_ID_COLUMN_NAME,  # Alternative name
        DOCUMENT_TITLE_COLUMN_NAME.lower(): DOCUMENT_TITLE_COLUMN_NAME,
        "source_identifier": FILE_ID_COLUMN_NAME,  # Alternative name
        PROCESSED_DATETIME_FIELD.lower(): PROCESSED_DATETIME_FIELD,
        TIMESTAMP_COLUMN_NAME.lower(): TIMESTAMP_COLUMN_NAME,
        ORDER_COLUMN_NAME.lower(): ORDER_COLUMN_NAME,
        URL_COLUMN_NAME.lower(): URL_COLUMN_NAME,
        # metadata and source_metadata are NOT in normal_columns_map - they go to metadata
    }
    # Identify which columns to map directly vs put in metadata
    mapped_cols = {}  # {source_col_name: unified_col_name}
    metadata_cols = []

    for col in source_columns:
        col_lower = col.lower()

        # Check if it's a normal column (maps directly to unified structure)
        if col_lower in normal_columns_map:
            unified_col_name = normal_columns_map[col_lower]
            mapped_cols[col] = unified_col_name
            LOGGER.debug(f"Column '{col}' mapped to unified column '{unified_col_name}'")

        # Check if it should be excluded (source_id, processed_datetime)
        elif col_lower == SOURCE_ID_COLUMN_NAME.lower():
            LOGGER.debug(f"Column '{col}' is source_id (handled separately)")

        # Everything else goes into metadata JSONB
        else:
            metadata_cols.append(col)
            LOGGER.debug(f"Column '{col}' will be added to metadata JSONB")

    return mapped_cols, metadata_cols


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
    try:
        # Use get_sanitize_names to get the correct collection name
        _, _, new_collection_name = get_sanitize_names(
            organization_id=organization_id,
            embedding_model_reference=embedding_model,
        )

        if not source_collections:
            LOGGER.warning(
                f"No source collections provided for organization {organization_id}, skipping collection merge."
            )
            return False

        LOGGER.info(f"Merging {len(source_collections)} collections into {new_collection_name}")

        # Check if target collection already exists and has data
        try:
            if await qdrant_service.collection_exists_async(new_collection_name):
                point_count = await qdrant_service.count_points_async(new_collection_name)
                if point_count > 0:
                    LOGGER.info(
                        f"Collection {new_collection_name} already exists with {point_count} points, skipping merge"
                    )
                    return False
                else:
                    LOGGER.info(f"Collection {new_collection_name} exists but is empty, continuing migration")
        except Exception as e:
            LOGGER.warning(
                f"Error checking if target collection {new_collection_name} exists: {str(e)}, continuing..."
            )

        # Find first valid source collection to get config from
        first_valid_collection = None
        first_valid_collection_name = None
        skipped_collections = []
        for source_id, collection_name in source_collections:
            try:
                if await qdrant_service.collection_exists_async(collection_name):
                    first_valid_collection = (source_id, collection_name)
                    first_valid_collection_name = collection_name
                    LOGGER.info(f"Found first valid collection: {collection_name} (source_id: {source_id})")
                    break
                else:
                    skipped_collections.append((source_id, collection_name))
                    LOGGER.warning(
                        f"Source collection {collection_name} does not exist in "
                        f"Qdrant (source_id: {source_id}), skipping."
                    )
            except Exception as e:
                skipped_collections.append((source_id, collection_name))
                LOGGER.warning(
                    f"Error checking if collection {collection_name} exists "
                    f"(source_id: {source_id}): {str(e)}, trying next..."
                )
                continue

        if not first_valid_collection:
            LOGGER.warning(
                f"No valid source collections found for organization {organization_id} with "
                f"embedding model {embedding_model}. Skipped {len(skipped_collections)} collection(s): "
                f"{[c[1] for c in skipped_collections]}. Skipping collection merge."
            )
            return False

        if skipped_collections:
            LOGGER.info(
                f"Skipped {len(skipped_collections)} collection(s) while finding first valid collection: "
                f"{[(sid, cname) for sid, cname in skipped_collections]}"
            )

        # Get collection config from first valid source collection
        try:
            collection_info = await qdrant_service._send_request_async(
                method="GET", endpoint=f"collections/{first_valid_collection_name}"
            )

            if not collection_info or "result" not in collection_info:
                LOGGER.error(
                    f"Could not get collection info for {first_valid_collection_name}, skipping collection merge"
                )
                return False

            collection_config = collection_info["result"]["config"]
            vector_size = collection_config["params"]["vectors"]["size"]
            distance = collection_config["params"]["vectors"]["distance"]

            # Create target collection if it doesn't exist
            if not await qdrant_service.collection_exists_async(new_collection_name):
                await qdrant_service.create_collection_async(
                    new_collection_name, vector_size=vector_size, distance=distance
                )
                LOGGER.info(f"Created collection {new_collection_name}")

            await qdrant_service.create_index_if_needed_async(
                collection_name=new_collection_name,
                field_name=SOURCE_ID_COLUMN_NAME,
                field_schema_type=FieldSchema.KEYWORD,
            )
            LOGGER.info(f"Created index on {SOURCE_ID_COLUMN_NAME} for collection {new_collection_name}")
        except Exception as e:
            LOGGER.error(
                f"Error setting up target collection {new_collection_name}: {str(e)}, skipping collection merge"
            )
            return False

        # Copy all points from source collections to new collection, adding source_id
        all_points = []
        collections_processed = 0
        collections_failed = 0
        skipped_collections_list = []  # Track which collections were skipped

        for source_id, collection_name in source_collections:
            try:
                if not await qdrant_service.collection_exists_async(collection_name):
                    LOGGER.warning(
                        f"Source collection {collection_name} does not exist in Qdrant "
                        f"(source_id: {source_id}), skipping."
                    )
                    collections_failed += 1
                    skipped_collections_list.append((source_id, collection_name, "does not exist"))
                    continue

                offset = None
                batch_size = 1000
                collection_points = 0

                while True:
                    try:
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

                        for point in batch_points:
                            if "payload" not in point:
                                point["payload"] = {}
                            point["payload"][SOURCE_ID_COLUMN_NAME] = source_id

                        all_points.extend(batch_points)
                        collection_points += len(batch_points)
                        offset = result.get("next_page_offset")

                        if not offset:
                            break
                    except Exception as e:
                        LOGGER.error(
                            f"Error scrolling points from collection {collection_name} for source "
                            f"{source_id}: {str(e)}. Continuing with next collection..."
                        )
                        break

                if collection_points > 0:
                    LOGGER.info(
                        f"Collected {collection_points} points from collection "
                        f"{collection_name} (source_id: {source_id})."
                    )
                    collections_processed += 1
                else:
                    LOGGER.warning(
                        f"No points collected from collection {collection_name} (source_id: {source_id}), skipping"
                    )
                    collections_failed += 1
                    skipped_collections_list.append((source_id, collection_name, "no points"))
            except Exception as e:
                LOGGER.error(
                    f"Error processing collection {collection_name} for source {source_id}: {str(e)}. "
                    f"Continuing with next collection..."
                )
                collections_failed += 1
                skipped_collections_list.append((source_id, collection_name, f"error: {str(e)}"))
                continue

        if all_points:
            LOGGER.info(f"Inserting {len(all_points)} points into collection {new_collection_name}")
            batch_size = 100
            inserted_count = 0
            failed_batches = 0

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
                        f"Error inserting batch {i // batch_size + 1} into collection {new_collection_name}: "
                        f"{str(e)}. Batch size: {len(batch)}. Continuing with next batch..."
                    )
                    failed_batches += 1
                    # Continue with next batch instead of raising
                    continue

            if inserted_count > 0:
                LOGGER.info(f"Successfully migrated {inserted_count} points to {new_collection_name}")
            if failed_batches > 0:
                LOGGER.warning(f"Failed to insert {failed_batches} batch(es) into {new_collection_name}")
        else:
            warning_msg = (
                f"No points to migrate to {new_collection_name} from {len(source_collections)} source collections. "
                f"Processed: {collections_processed}, Skipped: {collections_failed}"
            )
            if skipped_collections_list:
                skipped_details = ", ".join([
                    f"{cname} (source_id: {sid}, reason: {reason})" for sid, cname, reason in skipped_collections_list
                ])
                warning_msg += f". Skipped collections: {skipped_details}"
            LOGGER.warning(warning_msg)
            return False

        # NOTE: Old collections are NOT deleted here to allow for rollback.
        # They will be deleted in a subsequent migration/PR after verifying the migration was successful.
        summary_msg = (
            f"Migration completed for {new_collection_name}. "
            f"Processed {collections_processed} collection(s), skipped {collections_failed} collection(s). "
            f"Total collections: {len(source_collections)}. "
            f"Old collections are preserved for now and will be deleted in a subsequent PR."
        )
        if skipped_collections_list:
            skipped_details = ", ".join([
                f"{cname} (source_id: {sid}, reason: {reason})" for sid, cname, reason in skipped_collections_list
            ])
            summary_msg += f" Skipped collections: {skipped_details}"
        LOGGER.info(summary_msg)

        return True
    except Exception as e:
        LOGGER.error(
            f"Unexpected error in _merge_collections for organization {organization_id} "
            f"with embedding model {embedding_model}: {str(e)}. Continuing with next organization..."
        )
        return False


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
        LOGGER.warning(f"No source tables provided for organization {organization_id}, skipping table merge")
        return False

    schema_name, new_table_name, _ = get_sanitize_names(organization_id)  # Use public schema for all tables

    LOGGER.info(f"Merging {len(source_tables)} tables into {schema_name}.{new_table_name} in ingestion DB")

    # Check if target table already exists and has data
    table_exists = _check_table_exists(ingestion_db_connection, schema_name, new_table_name)
    LOGGER.info(f"Checking table existence: schema={schema_name}, table={new_table_name}, exists={table_exists}")

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

    LOGGER.info(f"Creating table {schema_name}.{new_table_name}")
    _create_table_from_definition(ingestion_db_connection, UNIFIED_TABLE_DEFINITION, schema_name, new_table_name)
    LOGGER.info(f"Table {schema_name}.{new_table_name} created/verified in ingestion database")

    # Ensure composite primary key exists (in case table was created before definition update)
    _ensure_composite_primary_key(ingestion_db_connection, schema_name, new_table_name)

    LOGGER.info(f"=== Starting merge of {len(source_tables)} source tables into {schema_name}.{new_table_name} ===")
    sources_processed = 0
    sources_skipped = 0
    total_rows_inserted = 0

    for idx, (source_id, schema, table_name, source_type) in enumerate(source_tables, 1):
        LOGGER.info(f"--- Processing source {idx}/{len(source_tables)}: {source_id} from {schema}.{table_name} ---")

        if schema and "test" in schema.lower():
            LOGGER.info(f"Skipping test source: {schema}.{table_name} (source_id: {source_id})")
            sources_skipped += 1
            continue
        if table_name and "test" in table_name.lower():
            LOGGER.info(f"Skipping test source: {schema}.{table_name} (source_id: {source_id})")
            sources_skipped += 1
            continue

        if not _check_table_exists(ingestion_db_connection, schema, table_name):
            LOGGER.warning(
                f"Source table {schema}.{table_name} does not exist, skipping migration for source {source_id}"
            )
            sources_skipped += 1
            continue

        try:
            source_row_count = ingestion_db_connection.execute(
                text(f'SELECT COUNT(*) FROM "{schema}"."{table_name}"')
            ).scalar()
            LOGGER.info(f"Source table {schema}.{table_name} has {source_row_count} rows to migrate")
        except Exception as e:
            LOGGER.warning(f"Could not count rows in source table {schema}.{table_name}: {e}")
            source_row_count = None

        # Get column info from source table in ingestion DB (including data types)
        source_columns, column_types = _get_table_column_info(ingestion_db_connection, schema, table_name)

        LOGGER.info(f"Source table {schema}.{table_name} has {len(source_columns)} columns: {source_columns}")

        # Classify columns using helper function
        mapped_cols, metadata_cols = _classify_columns(source_columns, column_types)

        LOGGER.info(
            f"Column mapping for {schema}.{table_name}: mapped={list(mapped_cols.keys())}, metadata={metadata_cols}"
        )

        select_parts = _build_select_parts_for_migration(source_id, mapped_cols, metadata_cols, column_types)

        insert_sql = f"""
            INSERT INTO "{schema_name}"."{new_table_name}"
            ({PROCESSED_DATETIME_FIELD}, {SOURCE_ID_COLUMN_NAME}, {CHUNK_ID_COLUMN_NAME},
            "{ORDER_COLUMN_NAME}", {FILE_ID_COLUMN_NAME}, {DOCUMENT_TITLE_COLUMN_NAME},
            {URL_COLUMN_NAME}, {CHUNK_COLUMN_NAME}, {TIMESTAMP_COLUMN_NAME}, {METADATA_COLUMN_NAME})
            SELECT {", ".join(select_parts)}
            FROM "{schema}"."{table_name}"
            ON CONFLICT ({CHUNK_ID_COLUMN_NAME}, {SOURCE_ID_COLUMN_NAME}) DO NOTHING
        """

        LOGGER.debug(f"SQL INSERT for {schema}.{table_name}:\n{insert_sql}")

        try:
            # Get row count in target table before insertion
            rows_before = ingestion_db_connection.execute(
                text(f'SELECT COUNT(*) FROM "{schema_name}"."{new_table_name}"')
            ).scalar()

            # Execute INSERT
            ingestion_db_connection.execute(text(insert_sql))
            # No commit needed in autocommit mode

            # Get row count after insertion to verify actual insertions
            rows_after = ingestion_db_connection.execute(
                text(f'SELECT COUNT(*) FROM "{schema_name}"."{new_table_name}"')
            ).scalar()
            actual_rows_inserted = rows_after - rows_before
            total_rows_inserted += actual_rows_inserted

            LOGGER.info(
                f"✓ Successfully processed {schema}.{table_name}: "
                f"source had {source_row_count} rows, "
                f"inserted {actual_rows_inserted} new rows "
                f"(target table: {rows_before} → {rows_after} rows)"
            )
            sources_processed += 1
        except Exception as e:
            LOGGER.error(
                f"Error copying data from {schema}.{table_name} to {schema_name}.{new_table_name}: {str(e)}\n"
                f"SQL: {insert_sql}"
            )
            LOGGER.warning(
                f"FAILED to migrate table {schema}.{table_name} for source {source_id}. "
                f"Old table {schema}.{table_name} will remain unchanged."
            )
            continue

        # Note: We do NOT drop old tables - they are kept for safety
        LOGGER.info(f"Migration completed for {schema}.{table_name} (old table preserved)")

    # Log summary of merge operation
    LOGGER.info(f"=== Merge summary for {schema_name}.{new_table_name} ===")
    LOGGER.info(
        f"Total sources: {len(source_tables)}, "
        f"Processed: {sources_processed}, "
        f"Skipped: {sources_skipped}, "
        f"Total rows inserted: {total_rows_inserted}"
    )

    # Verify final row count in target table
    try:
        final_row_count = ingestion_db_connection.execute(
            text(f'SELECT COUNT(*) FROM "{schema_name}"."{new_table_name}"')
        ).scalar()
        LOGGER.info(f"Final row count in {schema_name}.{new_table_name}: {final_row_count} rows")
    except Exception as e:
        LOGGER.warning(f"Could not count final rows in target table: {e}")

    # Return True if migration was performed (table was created and/or data was migrated)
    return sources_processed > 0


async def _verify_table_collection_count_match(
    ingestion_db_connection,
    qdrant_service,
    organization_id: str,
    embedding_model: str,
    source_ids: list[str],
):
    """Verify that the row count in the unified table matches the point count in the unified Qdrant collection.

    The table contains rows for all sources in an organization, but we need to filter by source_id
    to compare with the collection which is specific to org+embedding_model.

    Args:
        ingestion_db_connection: Connection to ingestion database
        qdrant_service: QdrantService instance for the embedding model
        organization_id: Organization ID
        embedding_model: Embedding model reference
        source_ids: List of source IDs for this org+embedding_model combination

    Returns:
        tuple: (table_count, collection_count, match) where match is True if counts match
    """
    try:
        # Get unified table and collection names
        schema_name, table_name, collection_name = get_sanitize_names(
            organization_id=str(organization_id),
            embedding_model_reference=embedding_model,
        )

        # Count rows in table filtered by source_ids for this embedding model
        try:
            if source_ids:
                # Build SQL with IN clause for source_ids using parameterized query
                # Use tuple with IN clause for safe parameterization
                # Convert source_ids to tuple of UUIDs for the query
                placeholders = ", ".join([f":source_id_{i}" for i in range(len(source_ids))])
                params = {f"source_id_{i}": source_id for i, source_id in enumerate(source_ids)}
                table_count = ingestion_db_connection.execute(
                    text(
                        f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}" '
                        f'WHERE "{SOURCE_ID_COLUMN_NAME}" IN ({placeholders})'
                    ),
                    params,
                ).scalar()
            else:
                LOGGER.warning(
                    f"No source_ids provided for organization {organization_id} with model {embedding_model}, "
                    f"skipping table count"
                )
                return None, None, False
        except Exception as e:
            LOGGER.warning(
                f"Could not count rows in table {schema_name}.{table_name} for organization {organization_id}: {e}"
            )
            return None, None, False

        # Count points in Qdrant collection
        try:
            if await qdrant_service.collection_exists_async(collection_name):
                collection_count = await qdrant_service.count_points_async(collection_name)
            else:
                LOGGER.warning(
                    f"Collection {collection_name} does not exist for organization {organization_id} "
                    f"with embedding model {embedding_model}"
                )
                return table_count, 0, False
        except Exception as e:
            LOGGER.warning(
                f"Could not count points in collection {collection_name} for organization {organization_id}: {e}"
            )
            return table_count, None, False

        # Compare counts
        counts_match = table_count == collection_count

        if counts_match:
            LOGGER.info(
                f"✓ Count verification passed for organization {organization_id} with model {embedding_model}: "
                f"table={table_count}, collection={collection_count}"
            )
        else:
            LOGGER.error(
                f"✗ Count mismatch for organization {organization_id} with model {embedding_model}: "
                f"table={table_count}, collection={collection_count}, difference={abs(table_count - collection_count)}"
            )

        return table_count, collection_count, counts_match

    except Exception as e:
        LOGGER.error(f"Error verifying counts for organization {organization_id} with model {embedding_model}: {e}")
        return None, None, False


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
    # Connection to ingestion database (for reading and writing ingestion tables)
    if not settings.INGESTION_DB_URL:
        LOGGER.error("INGESTION_DB_URL is not set. No migration to do. Skipping.")
        return

    try:
        # Use autocommit mode for ingestion database to avoid transaction issues
        ingestion_db_engine = create_engine(settings.INGESTION_DB_URL, isolation_level="AUTOCOMMIT")
        ingestion_db_connection = ingestion_db_engine.connect()
        LOGGER.info("Successfully connected to ingestion database (autocommit mode)")

        # Get ALL sources with embedding model reference from principal database
        # Use op.get_bind() to stay within Alembic's transaction (no manual commit needed)
        result = op.get_bind().execute(
            text(
                """
                SELECT id, organization_id, database_schema, database_table_name, name,
                qdrant_collection_name, type, embedding_model_reference FROM data_sources
                WHERE database_table_name IS NOT NULL
                ORDER BY organization_id, embedding_model_reference
            """
            )
        )

        all_sources = result.fetchall()

        if not all_sources:
            LOGGER.info("No sources found to migrate")
            return

        org_sources = {}  # For tables: {org_id: [sources]}
        org_model_sources = {}  # For collections: {(org_id, embedding_model): [sources]}

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
            model_ref = embedding_model or DEFAULT_EMBEDDING_MODEL

            # Group by org_id for tables (all sources in an org go to the same table)
            if org_id not in org_sources:
                org_sources[org_id] = []
            org_sources[org_id].append((
                source_id,
                db_schema,
                db_table,
                qdrant_collection,
                name,
                source_type,
                model_ref,
            ))

            # Group by (org_id, embedding_model) for collections
            key = (org_id, model_ref)
            if key not in org_model_sources:
                org_model_sources[key] = []
            org_model_sources[key].append((
                source_id,
                db_schema,
                db_table,
                qdrant_collection,
                name,
                source_type,
                model_ref,
            ))

        trace_manager = TraceManager(project_name="migration")

        # Create QdrantService for each unique embedding model
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

        LOGGER.info(f"Unique embedding models: {unique_embedding_models}")

        # Track migration statistics
        orgs_with_table_migrations = 0
        orgs_with_collection_migrations = 0
        orgs_skipped = 0

        # STEP 1: Merge tables by organization (1 table per org, regardless of embedding model)
        LOGGER.info(f"=== STEP 1: Merging tables by organization === len(org_sources): {len(org_sources)}")
        for org_id, sources in org_sources.items():
            LOGGER.info(f"Processing organization {org_id} - {len(sources)} sources for table merge")

            source_tables = []
            for source_id, db_schema, db_table, qdrant_collection, name, source_type, emb_model in sources:
                if db_table:
                    source_tables.append((str(source_id), db_schema, db_table, source_type))

            # Merge tables in ingestion DB (1 table per org)
            tables_migrated = False
            if source_tables:
                tables_migrated = _merge_tables(ingestion_db_connection, str(org_id), source_tables)
                if tables_migrated:
                    orgs_with_table_migrations += 1
            else:
                LOGGER.warning(f"No source tables found for organization {org_id}, skipping table migration")

        # STEP 2: Merge collections by organization+embedding_model (1 collection per org+embedding)
        LOGGER.info("=== STEP 2: Merging collections by organization+embedding_model ===")
        for (org_id, embedding_model), sources in org_model_sources.items():
            LOGGER.info(
                f"Processing organization {org_id} with embedding model {embedding_model} "
                f"- {len(sources)} sources for collection merge"
            )

            source_collections = []
            for source_id, db_schema, db_table, qdrant_collection, name, source_type, emb_model in sources:
                if qdrant_collection:
                    source_collections.append((str(source_id), qdrant_collection))

            # Merge collections (collections are per org+model)
            # NOTE: Old collections are NOT deleted here - will be done in a subsequent PR
            # Use the QdrantService for this specific embedding model
            collections_migrated = False
            if source_collections:
                try:
                    qdrant_service = qdrant_services[embedding_model]
                    collections_migrated = asyncio.run(
                        _merge_collections(qdrant_service, str(org_id), source_collections, embedding_model)
                    )
                    if collections_migrated:
                        orgs_with_collection_migrations += 1
                except Exception as e:
                    LOGGER.error(
                        f"Error merging collections for organization {org_id} with embedding "
                        f"model {embedding_model}: {str(e)}. Continuing with next organization..."
                    )
                    continue
            else:
                LOGGER.warning(
                    f"No source collections found for organization {org_id} with "
                    f"model {embedding_model}, skipping collection migration"
                )

        # STEP 2.5: Verify table and collection counts match
        LOGGER.info("=== STEP 2.5: Verifying table and collection counts match ===")
        verification_passed = 0
        verification_failed = 0
        verification_skipped = 0

        for (org_id, embedding_model), sources in org_model_sources.items():
            try:
                # Get source_ids for this org+embedding_model combination
                source_ids = [str(source_id) for source_id, _, _, _, _, _, _ in sources]

                if not source_ids:
                    LOGGER.warning(
                        f"No source_ids found for organization {org_id} with model {embedding_model}, "
                        f"skipping verification"
                    )
                    verification_skipped += 1
                    continue

                # Get the QdrantService for this embedding model
                if embedding_model not in qdrant_services:
                    LOGGER.warning(
                        f"No QdrantService found for embedding model {embedding_model}, skipping verification"
                    )
                    verification_skipped += 1
                    continue

                qdrant_service = qdrant_services[embedding_model]

                # Verify counts
                table_count, collection_count, match = asyncio.run(
                    _verify_table_collection_count_match(
                        ingestion_db_connection,
                        qdrant_service,
                        str(org_id),
                        embedding_model,
                        source_ids,
                    )
                )

                if match:
                    verification_passed += 1
                elif table_count is not None and collection_count is not None:
                    verification_failed += 1
                else:
                    verification_skipped += 1

            except Exception as e:
                LOGGER.error(f"Error during verification for organization {org_id} with model {embedding_model}: {e}")
                verification_skipped += 1
                continue

        LOGGER.info(
            f"Verification summary: {verification_passed} passed, {verification_failed} failed, "
            f"{verification_skipped} skipped"
        )

        if verification_failed > 0:
            LOGGER.error(
                f"WARNING: {verification_failed} organization(s) have count mismatches "
                "between table and Qdrant collection. Please investigate before proceeding."
            )

        # STEP 3: Update data_sources table for all sources
        LOGGER.info("=== STEP 3: Updating data_sources table ===")
        for (org_id, embedding_model), sources in org_model_sources.items():
            # Use get_sanitize_names to get the correct names based on org and embedding model
            # Table name is the same for all sources in an org (regardless of embedding model)
            # Collection name is specific to org+embedding_model
            new_schema_name, new_table_name, new_collection_name = get_sanitize_names(
                organization_id=str(org_id),
                embedding_model_reference=embedding_model,
            )

            for source_id, db_schema, db_table, qdrant_collection, name, source_type, emb_model in sources:
                op.get_bind().execute(
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

            LOGGER.info(
                f"Updated data_sources for organization {org_id} with embedding model {embedding_model} "
                f"to point to table {new_table_name} and collection {new_collection_name}"
            )

        # NOTE: Old tables and collections are NOT deleted in this migration.
        # They are preserved to allow for rollback and will be deleted in a subsequent PR.
        # After this migration, all new ingestions will use the new unified structures
        # (via the updated data_sources table), so no new data will be written to old structures.

        total_orgs_processed = len(org_sources)
        if total_orgs_processed == 0:
            LOGGER.warning(
                "Migration completed but NO organizations were processed. "
                "This may indicate that no sources were found in data_sources table or all sources were skipped."
            )

        LOGGER.info(
            f"Migration Step 1/2 completed: "
            f"Processed {total_orgs_processed} organization(s), "
            f"migrated tables for {orgs_with_table_migrations} organization(s), "
            f"migrated collections for {orgs_with_collection_migrations} organization(s), "
            f"skipped {orgs_skipped} organization(s) (already migrated). "
            "Old structures preserved for rollback. They will be deleted in a subsequent PR."
        )

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
                    try:
                        row_count = ingestion_db_connection.execute(
                            text(f'SELECT COUNT(*) FROM "public"."{table_name}"')
                        ).scalar()
                        LOGGER.info(f"  - public.{table_name}: {col_count} columns, {row_count} rows")
                    except Exception as e:
                        LOGGER.warning(f"  - public.{table_name}: {col_count} columns (could not count rows: {e})")
            else:
                LOGGER.warning("No tables found in public schema matching pattern 'org_%'")
        except Exception as e:
            LOGGER.error(f"Error listing tables: {e}")

        LOGGER.info("=== MIGRATION END ===")
    finally:
        ingestion_db_connection.close()
        ingestion_db_engine.dispose()


def downgrade() -> None:
    """
    Downgrade migration: Revert data_sources to point back to old per-source tables/collections.
    Note: We don't delete the merged tables/collections, we just revert the references.
    """
    result = op.get_bind().execute(
        text(
            """
            SELECT id, organization_id, database_schema, database_table_name, name,
            qdrant_collection_name, type, embedding_model_reference
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
        sanitized_org_id = sanitize_filename(str(org_id))
        old_schema = f"org_{sanitized_org_id}"
        sanitized_source_id = sanitize_filename(str(source_id))
        old_table_name = f"source_{sanitized_source_id}"
        old_collection_name = f"{sanitized_source_id}_collection"

        op.get_bind().execute(
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
