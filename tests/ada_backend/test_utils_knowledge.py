"""Shared test utilities for knowledge-related tests."""

from engine.storage_service.db_utils import DBColumn, DBDefinition, PROCESSED_DATETIME_FIELD


def get_knowledge_chunks_table_definition(
    include_metadata: bool = True,
    include_bounding_boxes: bool = True,
    include_qdrant_fields: bool = False,
    processed_datetime_type: str = "VARCHAR",
    processed_datetime_default: str | None = None,
) -> DBDefinition:
    """
    Get a table definition for knowledge_chunks table.

    Args:
        include_metadata: Whether to include the metadata column (VARIANT)
        include_bounding_boxes: Whether to include the bounding_boxes column (VARCHAR)
        include_qdrant_fields: Whether to include Qdrant-specific fields
        processed_datetime_type: Type for PROCESSED_DATETIME_FIELD (VARCHAR or STRING)
        processed_datetime_default: Default value for PROCESSED_DATETIME_FIELD

    Returns:
        DBDefinition for knowledge_chunks table
    """
    columns = [
        DBColumn(
            name=PROCESSED_DATETIME_FIELD,
            type=processed_datetime_type,
            default=processed_datetime_default,
            is_nullable=True,
        ),
        DBColumn(name="chunk_id", type="VARCHAR", is_primary_key=True),
        DBColumn(name="file_id", type="VARCHAR", is_nullable=False),
        DBColumn(name="content", type="VARCHAR", is_nullable=False),
        DBColumn(name="document_title", type="VARCHAR", is_nullable=True),
        DBColumn(name="url", type="VARCHAR", is_nullable=True),
        DBColumn(name="last_edited_ts", type="VARCHAR", is_nullable=True),
    ]

    if include_metadata:
        columns.append(DBColumn(name="metadata", type="VARIANT", is_nullable=True))

    if include_bounding_boxes:
        columns.append(DBColumn(name="bounding_boxes", type="VARCHAR", is_nullable=True))

    if include_qdrant_fields:
        columns.append(DBColumn(name="metadata_to_keep_by_qdrant_field", type="VARCHAR", is_nullable=True))
        columns.append(DBColumn(name="not_kept_by_qdrant_chunk_field", type="VARIANT", is_nullable=True))

    return DBDefinition(columns=columns)
