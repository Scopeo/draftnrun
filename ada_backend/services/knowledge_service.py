import logging
from typing import Any, Dict, List
from uuid import UUID
import json

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.knowledge_repository import (
    delete_document,
    delete_chunk,
    get_chunk_rows_for_document,
    list_documents_for_source,
)
from ada_backend.repositories.source_repository import get_data_source_by_org_id
from ada_backend.schemas.knowledge_schema import (
    KnowledgeChunk,
    KnowledgeDocumentWithChunks,
    KnowledgeDocumentsListResponse,
    KnowledgeDocumentMetadata,
    KnowledgeDocumentOverview,
)
from ada_backend.services.ingestion_database_service import get_sql_local_service_for_ingestion
from ada_backend.services.knowledge.errors import (
    KnowledgeServiceDocumentNotFoundError,
    KnowledgeServiceInvalidEmbeddingModelReferenceError,
    KnowledgeServiceInvalidQdrantSchemaError,
    KnowledgeServiceQdrantCollectionCheckError,
    KnowledgeServiceQdrantCollectionNotFoundError,
    KnowledgeServiceQdrantMissingFieldsError,
    KnowledgeServiceQdrantServiceCreationError,
    KnowledgeServiceQdrantChunkDeletionError,
    KnowledgeSourceNotFoundError,
    KnowledgeServiceDBSourceConfigError,
    KnowledgeServiceDBChunkDeletionError,
)
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import QdrantService, QdrantCollectionSchema
from engine.trace.trace_context import get_trace_manager
from ada_backend.services.entity_factory import get_llm_provider_and_model

LOGGER = logging.getLogger(__name__)


def _deserialize_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _get_source_for_organization(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
) -> db.DataSource:
    source = get_data_source_by_org_id(
        session_sql_alchemy=session, organization_id=organization_id, source_id=source_id
    )
    if source is None:
        raise KnowledgeSourceNotFoundError(source_id=str(source_id), organization_id=str(organization_id))
    if not source.database_schema or not source.database_table_name:
        raise KnowledgeServiceDBSourceConfigError(
            f"Data source '{source_id}' " "is missing ingestion database identifiers (schema/table)"
        )
    return source


async def _validate_and_get_qdrant_service(source: db.DataSource) -> QdrantService:
    missing = []
    if not source.qdrant_collection_name:
        missing.append("qdrant_collection_name")
    if not source.qdrant_schema:
        missing.append("qdrant_schema")
    if not source.embedding_model_reference:
        missing.append("embedding_model_reference")

    if missing:
        raise KnowledgeServiceQdrantMissingFieldsError(source_id=str(source.id), missing=missing)

    try:
        QdrantCollectionSchema(**source.qdrant_schema)
    except ValidationError as e:
        raise KnowledgeServiceInvalidQdrantSchemaError(
            source_id=str(source.id),
            schema=source.qdrant_schema,
            reason=str(e),
        ) from e

    try:
        get_llm_provider_and_model(source.embedding_model_reference)
    except (ValueError, KeyError) as e:
        raise KnowledgeServiceInvalidEmbeddingModelReferenceError(
            source_id=str(source.id),
            embedding_model_reference=source.embedding_model_reference,
            reason=str(e),
        ) from e

    try:
        qdrant_service = _get_qdrant_service(source.qdrant_schema, source.embedding_model_reference)
    except Exception as e:
        raise KnowledgeServiceQdrantServiceCreationError(
            source_id=str(source.id),
            reason=str(e),
        ) from e

    try:
        exists = await qdrant_service.collection_exists_async(source.qdrant_collection_name)
    except Exception as e:
        raise KnowledgeServiceQdrantCollectionCheckError(
            source_id=str(source.id),
            collection_name=source.qdrant_collection_name,
            reason=str(e),
        ) from e

    if not exists:
        raise KnowledgeServiceQdrantCollectionNotFoundError(
            source_id=str(source.id), collection_name=source.qdrant_collection_name
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


def list_documents_service(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
) -> KnowledgeDocumentsListResponse:
    source = _get_source_for_organization(session, organization_id, source_id)
    sql_local_service = get_sql_local_service_for_ingestion()
    rows = list_documents_for_source(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
    )
    documents: List[KnowledgeDocumentOverview] = []
    for row in rows:
        documents.append(
            KnowledgeDocumentOverview(
                document_id=row.document_id,
                document_title=row.document_title,
                chunk_count=int(row.chunk_count),
                last_edited_ts=row.last_edited_ts,
            )
        )
    return KnowledgeDocumentsListResponse(total=len(documents), items=documents)


def get_document_with_chunks_service(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    document_id: str,
) -> KnowledgeDocumentWithChunks:
    source = _get_source_for_organization(session, organization_id, source_id)
    sql_local_service = get_sql_local_service_for_ingestion()
    session = sql_local_service.get_session()
    rows, table = get_chunk_rows_for_document(
        sql_local_service, source.database_schema, source.database_table_name, document_id
    )

    if not rows:
        LOGGER.error(
            f"Document with id='{document_id}' not found for source '{source_id}' in database table '{source.database_table_name}'"
        )
        raise KnowledgeServiceDocumentNotFoundError(
            document_id=document_id,
            source_id=source_id,
        )

    chunks: List[KnowledgeChunk] = []
    for row in rows:
        row_dict = {column.name: getattr(row, column.name) for column in table.columns}
        row_dict["metadata"] = _deserialize_json_field(row_dict.get("metadata"))
        row_dict["bounding_boxes"] = _deserialize_json_field(row_dict.get("bounding_boxes"))
        if row_dict["metadata"] is None:
            row_dict["metadata"] = {}
        chunks.append(KnowledgeChunk(**row_dict))

    first_chunk = chunks[0]
    metadata = first_chunk.metadata or {}
    document_metadata = KnowledgeDocumentMetadata(
        document_id=first_chunk.document_id,
        document_title=getattr(first_chunk, "document_title", None),
        url=getattr(first_chunk, "url", None),
        metadata=metadata,
        last_edited_ts=first_chunk.last_edited_ts,
        folder_name=metadata.get("folder_name") if isinstance(metadata, dict) else None,
    )

    return KnowledgeDocumentWithChunks(document=document_metadata, chunks=chunks)


def delete_document_service(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    document_id: str,
) -> None:
    source = _get_source_for_organization(session, organization_id, source_id)
    sql_local_service = get_sql_local_service_for_ingestion()
    delete_document(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        document_id=document_id,
    )


async def delete_chunk_service(
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
        raise KnowledgeServiceQdrantChunkDeletionError(
            chunk_id=chunk_id,
            collection_name=source.qdrant_collection_name,
            reason=str(e),
        ) from e

    try:
        delete_chunk(
            sql_local_service=sql_local_service,
            schema_name=source.database_schema,
            table_name=source.database_table_name,
            chunk_id=chunk_id,
        )
    except Exception as e:
        LOGGER.error(
            f"Failed to delete chunk from Table {source.database_table_name}"
            f"in Schema {source.database_schema}: {str(e)}",
            exc_info=True,
        )
        raise KnowledgeServiceDBChunkDeletionError(
            chunk_id=chunk_id,
            table_name=source.database_table_name,
            schema_name=source.database_schema,
            reason=str(e),
        ) from e
