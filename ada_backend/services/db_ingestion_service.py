import logging
import uuid
from typing import Optional
from uuid import UUID

from ada_backend.database import models as db
from ada_backend.database.setup_db import SessionLocal
from ada_backend.repositories.ingestion_task_repository import (
    update_ingestion_task as repo_update_ingestion_task,
)
from ada_backend.repositories.source_repository import create_source as repo_create_source
from ada_backend.schemas.ingestion_task_schema import SourceAttributes
from engine.llm_services.llm_service import EmbeddingService
from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.storage_service.local_service import SQLLocalService
from engine.trace.trace_manager import TraceManager
from ingestion_script.ingest_db_source import upload_db_source
from ingestion_script.utils import (
    UNIFIED_QDRANT_SCHEMA,
    UNIFIED_TABLE_DEFINITION,
    get_sanitize_names,
)
from settings import settings

LOGGER = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1024
DEFAULT_CHUNK_OVERLAP = 0

EMBEDDING_PROVIDER = "openai"
EMBEDDING_MODEL_NAME = "text-embedding-3-large"
EMBEDDING_MODEL_REF = f"{EMBEDDING_PROVIDER}:{EMBEDDING_MODEL_NAME}"


async def run_db_ingestion(
    organization_id: UUID,
    task_id: UUID,
    source_name: str,
    source_attributes: SourceAttributes,
    source_id: Optional[UUID] = None,
) -> None:
    source_type = db.SourceType.DATABASE

    source_db_url = source_attributes.source_db_url
    source_table_name = source_attributes.source_table_name
    id_column_name = source_attributes.id_column_name
    text_column_names = source_attributes.text_column_names

    missing = []
    if not source_db_url:
        missing.append("source_db_url")
    if not source_table_name:
        missing.append("source_table_name")
    if not id_column_name:
        missing.append("id_column_name")
    if not text_column_names:
        missing.append("text_column_names")
    if missing:
        raise ValueError(f"Missing required DATABASE attributes: {', '.join(missing)}")

    chunk_size = source_attributes.chunk_size or DEFAULT_CHUNK_SIZE
    chunk_overlap = source_attributes.chunk_overlap or DEFAULT_CHUNK_OVERLAP
    update_existing = source_attributes.update_existing or False

    if settings.INGESTION_DB_URL is None:
        raise ValueError("INGESTION_DB_URL is not set")

    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)

    is_update = source_id is not None
    result_source_id = source_id if is_update else uuid.uuid4()

    embedding_service = EmbeddingService(
        provider=EMBEDDING_PROVIDER,
        model_name=EMBEDDING_MODEL_NAME,
        trace_manager=TraceManager(project_name="ingestion"),
    )

    schema_name, table_name, qdrant_collection_name = get_sanitize_names(
        organization_id=str(organization_id),
        embedding_model_reference=EMBEDDING_MODEL_REF,
    )

    qdrant_schema = QdrantCollectionSchema(
        chunk_id_field=UNIFIED_QDRANT_SCHEMA.chunk_id_field,
        content_field=UNIFIED_QDRANT_SCHEMA.content_field,
        url_id_field=UNIFIED_QDRANT_SCHEMA.url_id_field,
        file_id_field=UNIFIED_QDRANT_SCHEMA.file_id_field,
        last_edited_ts_field=UNIFIED_QDRANT_SCHEMA.last_edited_ts_field,
        metadata_fields_to_keep=UNIFIED_QDRANT_SCHEMA.metadata_fields_to_keep,
        source_id_field=UNIFIED_QDRANT_SCHEMA.source_id_field,
    )

    metadata_column_names = source_attributes.metadata_column_names
    timestamp_column_name = source_attributes.timestamp_column_name
    metadata_fields_to_keep: set[str] = set(metadata_column_names) if metadata_column_names else set()
    metadata_field_types: dict[str, str] = {col: "VARCHAR" for col in metadata_fields_to_keep}
    if timestamp_column_name:
        metadata_fields_to_keep.add(timestamp_column_name)
        metadata_field_types[timestamp_column_name] = "DATETIME"
    qdrant_schema.metadata_fields_to_keep = metadata_fields_to_keep or None
    qdrant_schema.metadata_field_types = metadata_field_types or None

    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=qdrant_schema,
    )

    try:
        await upload_db_source(
            db_service=db_service,
            qdrant_service=qdrant_service,
            db_definition=UNIFIED_TABLE_DEFINITION,
            storage_schema_name=schema_name,
            storage_table_name=table_name,
            qdrant_collection_name=qdrant_collection_name,
            source_id=result_source_id,
            source_db_url=source_db_url,
            source_table_name=source_table_name,
            id_column_name=id_column_name,
            text_column_names=text_column_names,
            source_schema_name=source_attributes.source_schema_name,
            metadata_column_names=metadata_column_names,
            timestamp_column_name=timestamp_column_name,
            url_pattern=source_attributes.url_pattern,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            update_existing=update_existing,
            query_filter=source_attributes.query_filter,
            timestamp_filter=source_attributes.timestamp_filter,
        )
    except Exception as e:
        error_msg = f"Failed to ingest data from database: {e}"
        LOGGER.error(error_msg, exc_info=True)
        _update_task_status(
            organization_id=organization_id,
            task_id=task_id,
            source_name=source_name,
            source_type=source_type,
            status=db.TaskStatus.FAILED,
            source_id=result_source_id,
            result_metadata={"message": error_msg, "type": "error"},
        )
        raise

    if not is_update:
        _create_source_record(
            organization_id=organization_id,
            source_id=result_source_id,
            source_name=source_name,
            source_type=source_type,
            schema_name=schema_name,
            table_name=table_name,
            qdrant_collection_name=qdrant_collection_name,
            qdrant_schema=qdrant_schema,
            embedding_model_ref=EMBEDDING_MODEL_REF,
            attributes=source_attributes,
        )

    _update_task_status(
        organization_id=organization_id,
        task_id=task_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.COMPLETED,
        source_id=result_source_id,
    )

    LOGGER.info("Successfully ingested database source '%s' for organization %s", source_name, organization_id)


def _update_task_status(
    organization_id: UUID,
    task_id: UUID,
    source_name: str,
    source_type: db.SourceType,
    status: db.TaskStatus,
    source_id: Optional[UUID] = None,
    result_metadata: Optional[dict] = None,
) -> None:
    with SessionLocal() as session:
        repo_update_ingestion_task(
            session=session,
            organization_id=organization_id,
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            status=status,
            task_id=task_id,
            result_metadata=result_metadata,
        )


def _create_source_record(
    organization_id: UUID,
    source_id: UUID,
    source_name: str,
    source_type: db.SourceType,
    schema_name: str,
    table_name: str,
    qdrant_collection_name: str,
    qdrant_schema: QdrantCollectionSchema,
    embedding_model_ref: str,
    attributes: Optional[SourceAttributes] = None,
) -> None:
    session = SessionLocal()
    try:
        repo_create_source(
            session=session,
            organization_id=organization_id,
            source_name=source_name,
            source_type=source_type,
            database_table_name=table_name,
            database_schema=schema_name,
            qdrant_collection_name=qdrant_collection_name,
            qdrant_schema=qdrant_schema.to_dict(),
            embedding_model_reference=embedding_model_ref,
            attributes=attributes,
            source_id=source_id,
        )
    finally:
        session.close()
