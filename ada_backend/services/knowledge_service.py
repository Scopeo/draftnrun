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


def create_chunk_for_data_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    file_id: str,
    request: CreateKnowledgeChunkRequest,
) -> KnowledgeChunk:
    source = _get_source_for_organization(session, organization_id, source_id)
    sql_local_service = get_sql_local_service_for_ingestion()

    if not file_exists(sql_local_service, source.database_schema, source.database_table_name, file_id):
        raise ValueError(f"File '{file_id}' not found for source '{source_id}'")

    content = request.content
    if _count_tokens(content) > MAX_CHUNK_TOKENS:
        raise ValueError("Chunk exceeds maximum allowed token count of 8000")

    chunk_id = request.chunk_id or str(uuid4())
    metadata = request.metadata or {}
    bounding_boxes = request.bounding_boxes
    last_edited_ts = request.last_edited_ts or datetime.utcnow().isoformat()

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
    sql_local_service = get_sql_local_service_for_ingestion()

    chunk = get_chunk_by_id(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk_id=chunk_id,
    )

    content = request.content if request.content is not None else chunk.get("content", "")

    if _count_tokens(content) > MAX_CHUNK_TOKENS:
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
    sql_local_service = get_sql_local_service_for_ingestion()

    delete_chunk(
        sql_local_service=sql_local_service,
        schema_name=source.database_schema,
        table_name=source.database_table_name,
        chunk_id=chunk_id,
    )
