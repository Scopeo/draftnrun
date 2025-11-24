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
from ada_backend.services.knowledge.errors import (
    KnowledgeServiceChunkWrongSizeError,
    KnowledgeServiceQdrantConfigurationError,
    KnowledgeServiceQdrantOperationError,
    KnowledgeServiceSourceError,
    KnowledgeServiceFileNotFoundError,
    KnowledgeServiceDBSourceConfigError,
    KnowledgeServiceDBOperationError,
    KnowledgeServiceChunkNotFoundError,
)
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import QdrantService, QdrantCollectionSchema
from engine.trace.trace_context import get_trace_manager
from ada_backend.services.entity_factory import get_llm_provider_and_model
from engine.storage_service.db_utils import get_default_value_for_column_type

LOGGER = logging.getLogger(__name__)

MAX_CHUNK_TOKENS = 8000

_TOKEN_ENCODING = tiktoken.encoding_for_model("gpt-4o-mini")


def _count_tokens(text: str) -> int:
    return len(_TOKEN_ENCODING.encode(text))


def _check_token_size_chunk(chunk_content: str):
    token_count = _count_tokens(chunk_content)
    if token_count == 0:
        raise KnowledgeServiceChunkWrongSizeError(
            "Chunk content cannot be empty (zero tokens)."
            " Vector database requires non-empty content for embeddings."
        )
    if token_count > MAX_CHUNK_TOKENS:
        raise KnowledgeServiceChunkWrongSizeError("Chunk exceeds maximum allowed token count of 8000")


def _get_source_for_organization(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
) -> db.DataSource:
    source = get_data_source_by_org_id(
        session_sql_alchemy=session, organization_id=organization_id, source_id=source_id
    )
    if source is None:
        raise KnowledgeServiceSourceError(f"Data source '{source_id}' not found for organization '{organization_id}'")
    if not source.database_schema or not source.database_table_name:
        raise KnowledgeServiceDBSourceConfigError(
            f"Data source '{source_id}' " "is missing ingestion database identifiers (schema/table)"
        )
    return source


async def _validate_and_get_qdrant_service(source: db.DataSource) -> QdrantService:
    if not source.qdrant_collection_name:
        raise KnowledgeServiceQdrantConfigurationError(f"Data source '{source.id}' is missing qdrant_collection_name")
    if not source.qdrant_schema:
        raise KnowledgeServiceQdrantConfigurationError(f"Data source '{source.id}' is missing qdrant_schema")
    if not source.embedding_model_reference:
        raise KnowledgeServiceQdrantConfigurationError(
            f"Data source '{source.id}' is missing embedding_model_reference"
        )
    try:
        QdrantCollectionSchema(**source.qdrant_schema)
    except Exception as e:
        raise KnowledgeServiceQdrantConfigurationError(
            f"Data source '{source.id}' has invalid qdrant_schema: {str(e)}"
        )

    try:
        get_llm_provider_and_model(source.embedding_model_reference)
    except Exception as e:
        raise KnowledgeServiceQdrantConfigurationError(
            f"Data source '{source.id}' has invalid embedding_model_reference: {str(e)}"
        ) from e

    qdrant_service = _get_qdrant_service(source.qdrant_schema, source.embedding_model_reference)
    if not await qdrant_service.collection_exists_async(source.qdrant_collection_name):
        raise KnowledgeServiceQdrantConfigurationError(
            f"Data source '{source.id}' references "
            f"Qdrant collection '{source.qdrant_collection_name}' "
            "which does not exist"
        )

    return qdrant_service


def _get_qdrant_service(
    qdrant_schema: Dict[str, Any],
    embedding_model_reference: str,
) -> QdrantService:
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


async def _get_source_and_services(session: Session, organization_id: UUID, source_id: UUID):
    source = _get_source_for_organization(session, organization_id, source_id)
    qdrant_service = await _validate_and_get_qdrant_service(source)
    sql_local_service = get_sql_local_service_for_ingestion()
    return source, qdrant_service, sql_local_service


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
) -> KnowledgeChunk:
    """
    Build enriched KnowledgeChunk with all required fields from qdrant schema.
    Missing fields are populated with default values based on metadata types.

    Args:
        chunk_id: Chunk ID
        file_id: File ID
        content: Chunk content
        last_edited_ts: Last edited timestamp
        qdrant_schema: Qdrant collection schema defining required fields

    Returns:
        Enriched KnowledgeChunk with all required fields
    """
    chunk_data = {
        "chunk_id": chunk_id,
        "file_id": file_id,
        "content": content,
    }

    required_fields = {
        qdrant_schema.chunk_id_field,
        qdrant_schema.content_field,
        qdrant_schema.file_id_field,
    }

    if qdrant_schema.url_id_field:
        required_fields.add(qdrant_schema.url_id_field)
        chunk_data[qdrant_schema.url_id_field] = ""
    if qdrant_schema.last_edited_ts_field:
        required_fields.add(qdrant_schema.last_edited_ts_field)
        chunk_data[qdrant_schema.last_edited_ts_field] = last_edited_ts
    for field_name in qdrant_schema.metadata_fields_to_keep:
        required_fields.add(field_name)

    for field in required_fields:
        if field not in chunk_data:
            if qdrant_schema.metadata_field_types and field in qdrant_schema.metadata_field_types:
                field_type = qdrant_schema.metadata_field_types[field]
                try:
                    chunk_data[field] = get_default_value_for_column_type(field_type)
                except ValueError:
                    LOGGER.warning(
                        f"Unknown field type '{field_type}' for field '{field}', using empty string as default"
                    )
                    chunk_data[field] = ""
            else:
                chunk_data[field] = ""
    return KnowledgeChunk(**chunk_data)


async def _upsert_chunk_in_qdrant(
    qdrant_service: QdrantService,
    qdrant_collection_name: str,
    chunk: KnowledgeChunk,
    type_of_operation: str,
):
    try:
        chunk_dict = chunk.model_dump(exclude_none=True)
        chunk_dict.pop("processed_datetime", None)
        chunk_dict.pop("_processed_datetime", None)

        await qdrant_service.add_chunks_async(
            list_chunks=[chunk_dict],
            collection_name=qdrant_collection_name,
        )

        LOGGER.info(f"{type_of_operation} chunk {chunk.chunk_id} in Qdrant collection {qdrant_collection_name}")
    except Exception as e:
        LOGGER.error(f"Failed to add chunk to Qdrant: {str(e)}", exc_info=True)
        raise KnowledgeServiceQdrantOperationError(
            f"Failed to {type_of_operation.lower()} chunk {chunk.chunk_id} in Qdrant: {str(e)}"
        ) from e


async def create_chunk_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    file_id: str,
    request: CreateKnowledgeChunkRequest,
) -> KnowledgeChunk:
    source, qdrant_service, sql_local_service = await _get_source_and_services(session, organization_id, source_id)

    if not file_exists(sql_local_service, source.database_schema, source.database_table_name, file_id):
        raise KnowledgeServiceFileNotFoundError(f"File '{file_id}' not found for source '{source_id}'")

    content = request.content

    _check_token_size_chunk(content)

    chunk_id = request.chunk_id or str(uuid4())
    last_edited_ts = request.last_edited_ts or datetime.utcnow().isoformat()

    minimal_chunk = KnowledgeChunk(
        chunk_id=chunk_id,
        file_id=file_id,
        content=content,
        last_edited_ts=last_edited_ts,
    )

    qdrant_collection_schema = QdrantCollectionSchema(**source.qdrant_schema)
    enriched_chunk = _build_enriched_chunk(
        chunk_id=minimal_chunk.chunk_id,
        file_id=minimal_chunk.file_id,
        content=minimal_chunk.content,
        last_edited_ts=minimal_chunk.last_edited_ts,
        qdrant_schema=qdrant_collection_schema,
    )

    await _upsert_chunk_in_qdrant(
        qdrant_service=qdrant_service,
        qdrant_collection_name=source.qdrant_collection_name,
        chunk=enriched_chunk,
        type_of_operation="Created",
    )

    chunk = create_chunk(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk=minimal_chunk,
    )

    return chunk


async def update_chunk_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    chunk_id: str,
    request: UpdateKnowledgeChunkRequest,
) -> KnowledgeChunk:
    source, qdrant_service, sql_local_service = await _get_source_and_services(session, organization_id, source_id)

    existing_qdrant_chunk_dict = await _get_chunk_from_qdrant_by_id(
        chunk_id, source.qdrant_collection_name, qdrant_service
    )

    updated_content = request.content if request.content is not None else existing_qdrant_chunk_dict["content"]
    updated_last_edited_ts = (
        request.last_edited_ts if request.last_edited_ts is not None else datetime.utcnow().isoformat()
    )

    _check_token_size_chunk(updated_content)

    updated_chunk_for_qdrant = _get_updated_payload_chunk_for_update(
        content=updated_content, last_edited_ts=updated_last_edited_ts, payload=existing_qdrant_chunk_dict
    )
    await _upsert_chunk_in_qdrant(
        qdrant_service=qdrant_service,
        qdrant_collection_name=source.qdrant_collection_name,
        chunk=updated_chunk_for_qdrant,
        type_of_operation="Updated",
    )

    existing_chunk_dict_from_table = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk_id=chunk_id,
    )

    updated_chunk_for_table = _get_updated_payload_chunk_for_update(
        content=updated_content,
        last_edited_ts=updated_last_edited_ts,
        payload=existing_chunk_dict_from_table,
    )

    updated_chunk = update_chunk(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk=updated_chunk_for_table,
    )

    return updated_chunk


async def delete_chunk_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    chunk_id: str,
) -> None:
    source, qdrant_service, sql_local_service = await _get_source_and_services(session, organization_id, source_id)
    qdrant_collection_schema = qdrant_service._get_schema(source.qdrant_collection_name)
    try:
        await qdrant_service.delete_chunks_async(
            point_ids=[chunk_id],
            id_field=qdrant_collection_schema.chunk_id_field,
            collection_name=source.qdrant_collection_name,
        )
        LOGGER.info(f"Deleted chunk {chunk_id} from Qdrant collection {source.qdrant_collection_name}")
    except Exception as e:
        LOGGER.error(f"Failed to delete chunk from Qdrant: {str(e)}", exc_info=True)
        raise KnowledgeServiceQdrantOperationError(f"Failed to delete chunk {chunk_id} from Qdrant: {str(e)}") from e

    try:
        delete_chunk(
            sql_local_service=sql_local_service,
            schema_name=source.database_schema,
            table_name=source.database_table_name,
            chunk_id=chunk_id,
        )
    except KnowledgeServiceChunkNotFoundError:
        raise
    except Exception as e:
        LOGGER.error(
            f"Failed to delete chunk from Table {source.database_table_name}"
            f"in Schema {source.database_schema}: {str(e)}",
            exc_info=True,
        )
        raise KnowledgeServiceDBOperationError(
            f"Failed to delete chunk {chunk_id} "
            f"from Table {source.database_table_name} "
            f"in Schema {source.database_schema}: {str(e)}"
        ) from e


async def _get_chunk_from_qdrant_by_id(chunk_id: str, collection_name: str, qdrant_service: QdrantService):
    """
    Retrieve chunk from Qdrant by filtering on chunk_id field in payload.
    Uses filter approach instead of point ID to avoid UUID conversion issues.
    """
    try:
        chunk_id_field = qdrant_service.default_schema.chunk_id_field

        filter_on_chunk_id = {"should": [{"key": chunk_id_field, "match": {"any": [chunk_id]}}]}
        points = await qdrant_service.get_points_async(filter=filter_on_chunk_id, collection_name=collection_name)

        if points and len(points) > 0:
            point = points[0]
            chunk_data = point.get("payload")
            if not chunk_data:
                raise KnowledgeServiceQdrantOperationError(f"Chunk {chunk_id} found in Qdrant but payload is missing")
            return chunk_data
        else:
            raise KnowledgeServiceQdrantOperationError(
                f"Chunk {chunk_id} not found in Qdrant collection {collection_name}"
            )
    except KnowledgeServiceQdrantOperationError:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to get chunk from Qdrant: {str(e)}", exc_info=True)
        raise KnowledgeServiceQdrantOperationError(f"Failed to get chunk {chunk_id} from Qdrant: {str(e)}") from e


def _get_updated_payload_chunk_for_update(
    content: str, last_edited_ts: str, payload: Dict[str, Any]
) -> KnowledgeChunk:
    chunk_data = payload.copy()
    chunk_data["content"] = content
    chunk_data["last_edited_ts"] = last_edited_ts
    return KnowledgeChunk(**chunk_data)
