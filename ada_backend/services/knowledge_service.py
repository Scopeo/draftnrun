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
    update_file_metadata,
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
    UpdateKnowledgeFileRequest,
)
from ada_backend.services.ingestion_database_service import get_sql_local_service_for_ingestion
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import QdrantService, QdrantCollectionSchema
from engine.trace.trace_context import get_trace_manager
from ada_backend.services.entity_factory import get_llm_provider_and_model

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


def update_file_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    file_id: str,
    update_request: UpdateKnowledgeFileRequest,
) -> KnowledgeFileDetail:
    source = _get_source_for_organization(session, organization_id, source_id)
    sql_local_service = get_sql_local_service_for_ingestion()
    update_file_metadata(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        file_id=file_id,
        document_title=update_request.document_title,
        url=update_request.url,
        metadata=update_request.metadata,
    )
    return get_file_detail_for_data_source(session, organization_id, source_id, file_id)


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


def _upsert_chunk_in_qdrant(
    qdrant_service: QdrantService,
    qdrant_collection_name: str,
    chunk_id: str,
    chunk_dict: Dict[str, Any],
    type_of_operation: str,
):
    try:
        asyncio.run(
            qdrant_service.add_chunks_async(
                list_chunks=[chunk_dict],
                collection_name=qdrant_collection_name,
            )
        )
        LOGGER.info(f"{type_of_operation} chunk {chunk_id} in Qdrant collection {qdrant_collection_name}")
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
    metadata = request.metadata or {}
    bounding_boxes = request.bounding_boxes
    last_edited_ts = request.last_edited_ts or datetime.utcnow().isoformat()

    chunk_dict = {
        "chunk_id": chunk_id,
        "file_id": file_id,
        "content": content,
        "document_title": request.document_title,
        "url": request.url,
        "metadata": metadata,
        "bounding_boxes": bounding_boxes,
        "last_edited_ts": last_edited_ts,
    }

    _upsert_chunk_in_qdrant(
        qdrant_service=qdrant_service,
        qdrant_collection_name=source.qdrant_collection_name,
        chunk_id=chunk_id,
        chunk_dict=chunk_dict,
        type_of_operation="Created",
    )

    chunk_dict = create_chunk(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk_id=chunk_id,
        file_id=file_id,
        content=content,
        document_title=request.document_title,
        url=request.url,
        metadata=metadata,
        bounding_boxes=bounding_boxes,
        last_edited_ts=last_edited_ts,
    )

    return KnowledgeChunk(**chunk_dict)


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

    chunk = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk_id=chunk_id,
    )

    content = request.content if request.content is not None else chunk.get("content", "")

    token_count = _count_tokens(content)
    if token_count == 0:
        raise ValueError(
            "Chunk content cannot be empty (zero tokens). Vector database requires non-empty content for embeddings."
        )
    if token_count > MAX_CHUNK_TOKENS:
        raise ValueError("Chunk exceeds maximum allowed token count of 8000")

    update_payload: Dict[str, Any] = {}

    if request.content is not None:
        update_payload["content"] = request.content
    if request.document_title is not None:
        update_payload["document_title"] = request.document_title
    if request.url is not None:
        update_payload["url"] = request.url
    if request.metadata is not None:
        update_payload["metadata"] = request.metadata
    if request.bounding_boxes is not None:
        update_payload["bounding_boxes"] = request.bounding_boxes
    if request.last_edited_ts is not None:
        update_payload["last_edited_ts"] = request.last_edited_ts
    else:
        update_payload["last_edited_ts"] = datetime.utcnow().isoformat()

    updated_chunk_dict = {
        "chunk_id": chunk_id,
        "file_id": chunk.get("file_id", ""),
        "content": update_payload.get("content", chunk.get("content", "")),
        "document_title": update_payload.get("document_title", chunk.get("document_title")),
        "url": update_payload.get("url", chunk.get("url")),
        "metadata": update_payload.get("metadata", chunk.get("metadata", {})),
        "bounding_boxes": update_payload.get("bounding_boxes", chunk.get("bounding_boxes")),
        "last_edited_ts": update_payload.get("last_edited_ts", chunk.get("last_edited_ts")),
    }

    _upsert_chunk_in_qdrant(
        qdrant_service=qdrant_service,
        qdrant_collection_name=source.qdrant_collection_name,
        chunk_id=chunk_id,
        chunk_dict=updated_chunk_dict,
        type_of_operation="Updated",
    )

    updated_chunk = update_chunk(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk_id=chunk_id,
        update_data=update_payload,
    )

    return KnowledgeChunk(**updated_chunk)


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
