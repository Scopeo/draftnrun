import asyncio
import logging
from datetime import datetime
from typing import Any, Dict
from uuid import UUID, uuid4

import tiktoken
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.knowledge_repository import (
    delete_file,
    delete_chunk,
    get_file_with_chunks,
    get_chunk_by_id,
    list_files_for_source,
    file_exists,
    create_chunk,
    update_chunk,
)
from ada_backend.repositories.source_repository import get_data_source_by_org_id
from ada_backend.schemas.knowledge_schema import (
    CreateKnowledgeChunkRequest,
    KnowledgeChunk,
    KnowledgeFileDetail,
    KnowledgeFileListResponse,
    KnowledgeFileMetadata,
    KnowledgeFileSummary,
    UpdateKnowledgeChunkRequest,
)
from ada_backend.services.ingestion_database_service import get_sql_local_service_for_ingestion
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import QdrantService, QdrantCollectionSchema
from engine.trace.trace_context import get_trace_manager
from ada_backend.services.entity_factory import get_llm_provider_and_model
from engine.storage_service.local_service import SQLLocalService

LOGGER = logging.getLogger(__name__)

MAX_CHUNK_TOKENS = 8000

_TOKEN_ENCODING = tiktoken.encoding_for_model("gpt-4o-mini")


def _count_tokens(text: str) -> int:
    return len(_TOKEN_ENCODING.encode(text))


def _get_source_for_organization(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
) -> db.DataSource:
    source = get_data_source_by_org_id(
        session_sql_alchemy=session, organization_id=organization_id, source_id=source_id
    )
    if source is None:
        raise ValueError(f"Data source '{source_id}' not found for organization '{organization_id}'")
    if not source.database_schema or not source.database_table_name:
        raise ValueError(f"Data source '{source_id}' is missing ingestion database identifiers (schema/table)")
    return source


def _validate_and_get_qdrant_service(source: db.DataSource) -> QdrantService:
    """
    Validate Qdrant configuration and return a configured QdrantService.
    Validates that all required fields are present, schema is valid, embedding model is valid,
    and that the Qdrant collection exists.

    Args:
        source: The data source object

    Returns:
        QdrantService: Configured Qdrant service instance

    Raises:
        ValueError: If Qdrant configuration is incomplete, invalid, or collection doesn't exist
    """
    if not source.qdrant_collection_name:
        raise ValueError(f"Data source '{source.id}' is missing qdrant_collection_name")
    if not source.qdrant_schema:
        raise ValueError(f"Data source '{source.id}' is missing qdrant_schema")
    if not source.embedding_model_reference:
        raise ValueError(f"Data source '{source.id}' is missing embedding_model_reference")

    try:
        QdrantCollectionSchema(**source.qdrant_schema)
    except Exception as e:
        raise ValueError(f"Data source '{source.id}' has invalid qdrant_schema: {str(e)}") from e

    try:
        get_llm_provider_and_model(source.embedding_model_reference)
    except Exception as e:
        raise ValueError(f"Data source '{source.id}' has invalid embedding_model_reference: {str(e)}") from e

    qdrant_service = _get_qdrant_service(
        source.qdrant_collection_name, source.qdrant_schema, source.embedding_model_reference
    )
    if not qdrant_service.collection_exists(source.qdrant_collection_name):
        raise ValueError(
            f"Data source '{source.id}' references "
            f"Qdrant collection '{source.qdrant_collection_name}' which does not exist"
        )

    return qdrant_service


def _get_qdrant_service(
    qdrant_collection_name: str,
    qdrant_schema: Dict[str, Any],
    embedding_model_reference: str,
) -> QdrantService:
    """
    Create and configure a Qdrant service instance.

    Args:
        qdrant_collection_name: Name of the Qdrant collection
        qdrant_schema: Qdrant collection schema as a dictionary
        embedding_model_reference: Embedding model reference (e.g., "openai:text-embedding-3-large")

    Returns:
        QdrantService
    """
    trace_manager = get_trace_manager()
    provider, model_name = get_llm_provider_and_model(embedding_model_reference)

    embedding_service = EmbeddingService(
        trace_manager=trace_manager,
        provider=provider,
        model_name=model_name,
    )

    qdrant_collection_schema = QdrantCollectionSchema(**qdrant_schema)

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_collection_schema,
    )

    return qdrant_service


def list_files_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
) -> KnowledgeFileListResponse:
    source = _get_source_for_organization(session, organization_id, source_id)
    sql_local_service = get_sql_local_service_for_ingestion()
    files_payload = list_files_for_source(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
    )
    files = [KnowledgeFileSummary(**file_data) for file_data in files_payload]
    return KnowledgeFileListResponse(total=len(files), items=files)


def get_file_detail_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    file_id: str,
) -> KnowledgeFileDetail:
    source = _get_source_for_organization(session, organization_id, source_id)
    sql_local_service = get_sql_local_service_for_ingestion()
    payload = get_file_with_chunks(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        file_id=file_id,
    )
    file_metadata = KnowledgeFileMetadata(**payload["file"])
    chunks = [KnowledgeChunk(**chunk_dict) for chunk_dict in payload["chunks"]]
    return KnowledgeFileDetail(file=file_metadata, chunks=chunks)


def delete_file_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    file_id: str,
) -> None:
    source = _get_source_for_organization(session, organization_id, source_id)
    sql_local_service = get_sql_local_service_for_ingestion()
    delete_file(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        file_id=file_id,
    )


def _build_enriched_chunk(
    chunk_id: str,
    file_id: str,
    content: str,
    last_edited_ts: str,
    qdrant_schema: QdrantCollectionSchema,
    sql_local_service: SQLLocalService,
    schema_name: str,
    table_name: str,
) -> KnowledgeChunk:
    """
    Build enriched KnowledgeChunk with all required fields from qdrant schema.
    Missing fields are populated with default values based on table column types.

    Args:
        chunk_id: Chunk ID
        file_id: File ID
        content: Chunk content
        last_edited_ts: Last edited timestamp
        qdrant_schema: Qdrant collection schema defining required fields
        sql_local_service: SQL service to query table schema
        schema_name: Database schema name
        table_name: Table name

    Returns:
        Enriched KnowledgeChunk with all required fields
    """
    # Start with required fields
    chunk_data = {
        "chunk_id": chunk_id,
        "file_id": file_id,
        "content": content,
        "last_edited_ts": last_edited_ts,
    }

    # Get required fields from qdrant schema
    required_fields = {
        qdrant_schema.chunk_id_field,
        qdrant_schema.content_field,
        qdrant_schema.file_id_field,
    }

    if qdrant_schema.url_id_field:
        required_fields.add(qdrant_schema.url_id_field)
    if qdrant_schema.last_edited_ts_field:
        required_fields.add(qdrant_schema.last_edited_ts_field)

    # Add metadata_fields_to_keep as top-level fields on KnowledgeChunk
    if qdrant_schema.metadata_fields_to_keep:
        for field_name in qdrant_schema.metadata_fields_to_keep:
            if field_name not in chunk_data:
                # Get default value based on metadata field type if available
                from engine.storage_service.db_utils import get_default_value_for_column_type

                if qdrant_schema.metadata_field_types and field_name in qdrant_schema.metadata_field_types:
                    field_type = qdrant_schema.metadata_field_types[field_name]
                    default_value = get_default_value_for_column_type(field_type)
                else:
                    # Default to empty string if no type info
                    default_value = ""
                chunk_data[field_name] = default_value

    # Get table description to determine default values
    try:
        table_description = sql_local_service.describe_table(table_name=table_name, schema_name=schema_name)
        column_info_map = {col["name"].lower(): col for col in table_description}
    except Exception as e:
        LOGGER.warning(f"Could not get table description for {schema_name}.{table_name}: {str(e)}")
        column_info_map = {}

    # Add missing required fields with defaults
    for field in required_fields:
        if field not in chunk_data:
            column_info = column_info_map.get(field.lower())

            if column_info:
                from engine.storage_service.db_utils import get_default_value_for_column_type

                default_value = get_default_value_for_column_type(column_info.get("type", ""))
                chunk_data[field] = default_value
                LOGGER.debug(f"Added missing field '{field}' with default value {default_value} based on column type")
            else:
                chunk_data[field] = ""
                LOGGER.debug(f"Added missing field '{field}' with default empty string (column not found in table)")

    return KnowledgeChunk(**chunk_data)


def _upsert_chunk_in_qdrant(
    qdrant_service: QdrantService,
    qdrant_collection_name: str,
    chunk: KnowledgeChunk,
    type_of_operation: str,
):
    try:
        # Convert KnowledgeChunk to dict for Qdrant (exclude processed_datetime)
        chunk_dict = chunk.model_dump(exclude_none=True)
        chunk_dict.pop("processed_datetime", None)
        chunk_dict.pop("_processed_datetime", None)

        asyncio.run(
            qdrant_service.add_chunks_async(
                list_chunks=[chunk_dict],
                collection_name=qdrant_collection_name,
            )
        )
        LOGGER.info(f"{type_of_operation} chunk {chunk.chunk_id} in Qdrant collection {qdrant_collection_name}")
    except Exception as e:
        LOGGER.error(f"Failed to add chunk to Qdrant: {str(e)}", exc_info=True)
        raise


def create_chunk_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    file_id: str,
    request: CreateKnowledgeChunkRequest,
) -> KnowledgeChunk:
    source = _get_source_for_organization(session, organization_id, source_id)
    qdrant_service = _validate_and_get_qdrant_service(source)
    sql_local_service = get_sql_local_service_for_ingestion()

    if not file_exists(sql_local_service, source.database_schema, source.database_table_name, file_id):
        raise ValueError(f"File '{file_id}' not found for source '{source_id}'")

    content = request.content
    token_count = _count_tokens(content)
    if token_count == 0:
        raise ValueError(
            "Chunk content cannot be empty (zero tokens). Vector database requires non-empty content for embeddings."
        )
    if token_count > MAX_CHUNK_TOKENS:
        raise ValueError("Chunk exceeds maximum allowed token count of 8000")

    chunk_id = request.chunk_id or str(uuid4())
    last_edited_ts = request.last_edited_ts or datetime.utcnow().isoformat()

    qdrant_collection_schema = QdrantCollectionSchema(**source.qdrant_schema)
    chunk = _build_enriched_chunk(
        chunk_id=chunk_id,
        file_id=file_id,
        content=content,
        last_edited_ts=last_edited_ts,
        qdrant_schema=qdrant_collection_schema,
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
    )

    _upsert_chunk_in_qdrant(
        qdrant_service=qdrant_service,
        qdrant_collection_name=source.qdrant_collection_name,
        chunk=chunk,
        type_of_operation="Created",
    )

    chunk = create_chunk(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk=chunk,
    )

    return chunk


def update_chunk_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    chunk_id: str,
    request: UpdateKnowledgeChunkRequest,
) -> KnowledgeChunk:
    source = _get_source_for_organization(session, organization_id, source_id)
    qdrant_service = _validate_and_get_qdrant_service(source)
    sql_local_service = get_sql_local_service_for_ingestion()

    existing_chunk_dict = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk_id=chunk_id,
    )

    # Convert existing chunk to KnowledgeChunk
    existing_chunk = KnowledgeChunk(**existing_chunk_dict)

    # Apply modifications
    updated_content = request.content if request.content is not None else existing_chunk.content
    updated_last_edited_ts = (
        request.last_edited_ts if request.last_edited_ts is not None else datetime.utcnow().isoformat()
    )

    token_count = _count_tokens(updated_content)
    if token_count == 0:
        raise ValueError(
            "Chunk content cannot be empty (zero tokens). Vector database requires non-empty content for embeddings."
        )
    if token_count > MAX_CHUNK_TOKENS:
        raise ValueError("Chunk exceeds maximum allowed token count of 8000")

    # Create updated chunk by modifying the existing one
    updated_chunk_dict = existing_chunk.model_dump()
    updated_chunk_dict["content"] = updated_content
    updated_chunk_dict["last_edited_ts"] = updated_last_edited_ts
    updated_chunk = KnowledgeChunk(**updated_chunk_dict)

    _upsert_chunk_in_qdrant(
        qdrant_service=qdrant_service,
        qdrant_collection_name=source.qdrant_collection_name,
        chunk=updated_chunk,
        type_of_operation="Updated",
    )

    updated_chunk = update_chunk(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk=updated_chunk,
    )

    return updated_chunk


def delete_chunk_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    chunk_id: str,
) -> None:
    source = _get_source_for_organization(session, organization_id, source_id)
    qdrant_service = _validate_and_get_qdrant_service(source)
    sql_local_service = get_sql_local_service_for_ingestion()
    qdrant_collection_schema = qdrant_service._get_schema(source.qdrant_collection_name)
    try:
        asyncio.run(
            qdrant_service.delete_chunks_async(
                point_ids=[chunk_id],
                id_field=qdrant_collection_schema.chunk_id_field,
                collection_name=source.qdrant_collection_name,
            )
        )
        LOGGER.info(f"Deleted chunk {chunk_id} from Qdrant collection {source.qdrant_collection_name}")
    except Exception as e:
        LOGGER.error(f"Failed to delete chunk from Qdrant: {str(e)}", exc_info=True)
        raise

    delete_chunk(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk_id=chunk_id,
    )
