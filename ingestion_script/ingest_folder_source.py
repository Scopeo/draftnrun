import logging
from uuid import UUID
from typing import Optional

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import IngestionTaskUpdate
from ada_backend.schemas.source_schema import DataSourceSchema
from data_ingestion.document.document_chunking import (
    document_chunking_mapping,
    get_chunks_dataframe_from_doc,
)
from data_ingestion.document.folder_management.folder_management import FolderManager
from data_ingestion.document.folder_management.google_drive_folder_management import GoogleDriveFolderManager
from data_ingestion.document.folder_management.s3_folder_management import S3FolderManager
from data_ingestion.document.supabase_file_uploader import sync_files_to_supabase
from engine.llm_services.llm_service import EmbeddingService, VisionService
from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.storage_service.db_service import DBService
from engine.storage_service.db_utils import PROCESSED_DATETIME_FIELD, DBColumn, DBDefinition, create_db_if_not_exists
from engine.storage_service.local_service import SQLLocalService
from engine.trace.trace_manager import TraceManager
from ingestion_script.utils import (
    create_source,
    get_sanitize_names,
    update_ingestion_task,
    get_first_available_embeddings_custom_llm,
    get_first_available_multimodal_custom_llm,
)
from settings import settings

LOGGER = logging.getLogger(__name__)

ID_COLUMN_NAME = "chunk_id"
TIMESTAMP_COLUMN_NAME = "last_edited_ts"
META_DATA_TO_KEEP = [
    "folder_name",
    "page_number",
]

FILE_TABLE_DEFINITION = DBDefinition(
    columns=[
        DBColumn(name=PROCESSED_DATETIME_FIELD, type="DATETIME", default="CURRENT_TIMESTAMP"),
        DBColumn(name=ID_COLUMN_NAME, type="VARCHAR", is_primary_key=True),
        DBColumn(name="file_id", type="VARCHAR"),
        DBColumn(name="content", type="VARCHAR"),
        DBColumn(name="document_title", type="VARCHAR"),
        DBColumn(name="url", type="VARCHAR"),
        DBColumn(name="bounding_boxes", type="VARCHAR"),
        DBColumn(name=TIMESTAMP_COLUMN_NAME, type="VARCHAR"),
        DBColumn(name="metadata", type="VARIANT"),
    ]
)

QDRANT_SCHEMA = QdrantCollectionSchema(
    chunk_id_field=ID_COLUMN_NAME,
    content_field="content",
    url_id_field="url",
    file_id_field="file_id",
    last_edited_ts_field=TIMESTAMP_COLUMN_NAME,
    metadata_fields_to_keep=["metadata"],
)


def load_llms_services():
    if settings.INGESTION_VIA_CUSTOM_MODEL:
        vision_completion_service = get_first_available_multimodal_custom_llm()
        fallback_vision_llm_service = vision_completion_service
        if vision_completion_service is None:
            raise ValueError(
                "No multimodal custom LLM found. Please set up a custom model for ingestion"
                "or check that your providers for custom llm are unique."
            )
    else:
        vision_completion_service = VisionService(
            provider="google",
            model_name="gemini-2.0-flash-exp",
            trace_manager=TraceManager(project_name="ingestion"),
        )
        fallback_vision_llm_service = VisionService(
            provider="openai",
            model_name="gpt-4.1-mini",
            trace_manager=TraceManager(project_name="ingestion"),
        )

    return vision_completion_service, fallback_vision_llm_service


def load_embedding_service():
    if settings.INGESTION_VIA_CUSTOM_MODEL:
        return get_first_available_embeddings_custom_llm()
    else:
        return EmbeddingService(
            provider="openai",
            model_name="text-embedding-3-large",
            trace_manager=TraceManager(project_name="ingestion"),
        )


async def sync_chunks_to_qdrant(
    table_schema: str,
    table_name: str,
    collection_name: str,
    db_service: DBService,
    qdrant_service: QdrantService,
    sql_query_filter: Optional[str] = None,
    query_filter_qdrant: Optional[dict] = None,
) -> None:
    chunks_df = db_service.get_table_df(
        table_name,
        schema_name=table_schema,
        sql_query_filter=sql_query_filter,
    )
    LOGGER.info(f"Syncing chunks to Qdrant collection {collection_name} with {len(chunks_df)} rows")
    if not await qdrant_service.collection_exists_async(collection_name):
        await qdrant_service.create_collection_async(collection_name)
    await qdrant_service.sync_df_with_collection_async(
        df=chunks_df,
        collection_name=collection_name,
        query_filter_qdrant=query_filter_qdrant,
    )


async def ingest_google_drive_source(
    folder_id: str,
    organization_id: str,
    source_name: str,
    task_id: UUID,
    save_supabase: bool = True,
    access_token: str = None,
    add_doc_description_to_chunks: bool = False,
    chunk_size: Optional[int] = 1024,
    chunk_overlap: Optional[int] = 0,
) -> None:
    LOGGER.info(
        f"[INGESTION_SOURCE] Starting GOOGLE DRIVE ingestion - Source: '{source_name}', "
        f"Folder ID: '{folder_id}', Organization: '{organization_id}', Task: '{task_id}'"
    )
    LOGGER.info(
        f"[INGESTION_CONFIG] Supabase save: {save_supabase}, "
        f"Add descriptions: {add_doc_description_to_chunks}, Chunk size: {chunk_size}"
    )

    # TODO: see how we can change whole code to use id instead of path
    path = "https://drive.google.com/drive/folders/" + folder_id
    folder_manager = GoogleDriveFolderManager(path=path, access_token=access_token)
    source_type = db.SourceType.GOOGLE_DRIVE
    await _ingest_folder_source(
        folder_manager=folder_manager,
        organization_id=organization_id,
        source_name=source_name,
        source_type=source_type,
        task_id=task_id,
        save_supabase=save_supabase,
        add_doc_description_to_chunks=add_doc_description_to_chunks,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


async def ingest_local_folder_source(
    list_of_files_to_ingest: list[dict],
    organization_id: str,
    source_name: str,
    task_id: UUID,
    save_supabase: bool = True,
    add_doc_description_to_chunks: bool = False,
    chunk_size: Optional[int] = 1024,
    chunk_overlap: Optional[int] = 0,
) -> None:
    LOGGER.info(
        f"[INGESTION_SOURCE] Starting LOCAL ingestion - Source: '{source_name}', "
        f"Organization: '{organization_id}', Task: '{task_id}'"
    )
    LOGGER.info(
        f"[INGESTION_CONFIG] Files count: {len(list_of_files_to_ingest)}, Supabase save: {save_supabase}, "
        f"Add descriptions: {add_doc_description_to_chunks}, Chunk size: {chunk_size}"
    )

    folder_manager = S3FolderManager(folder_payload=list_of_files_to_ingest)
    source_type = db.SourceType.LOCAL
    await _ingest_folder_source(
        folder_manager=folder_manager,
        organization_id=organization_id,
        source_name=source_name,
        source_type=source_type,
        task_id=task_id,
        save_supabase=save_supabase,
        add_doc_description_to_chunks=add_doc_description_to_chunks,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    folder_manager.clean_bucket()


async def _ingest_folder_source(
    folder_manager: FolderManager,
    organization_id: str,
    source_name: str,
    source_type: db.SourceType,
    task_id: UUID,
    save_supabase: bool = True,
    add_doc_description_to_chunks: bool = False,
    chunk_size: Optional[int] = 1024,
    chunk_overlap: Optional[int] = 0,
) -> None:
    ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.FAILED,
    )
    if settings.USE_LLM_FOR_PDF_PARSING:
        try:
            vision_completion_service, fallback_vision_llm_service = load_llms_services()
        except ValueError as e:
            LOGGER.error(f"Failed to load LLM services: {str(e)}")
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=ingestion_task,
            )
            return
    else:
        vision_completion_service = None
        fallback_vision_llm_service = None

    try:
        embedding_service = load_embedding_service()
    except ValueError as e:
        LOGGER.error(f"Failed to load embedding service: {str(e)}")
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        return

    db_table_schema, db_table_name, qdrant_collection_name = get_sanitize_names(
        source_name=source_name,
        organization_id=organization_id,
    )

    if settings.INGESTION_DB_URL is None:
        raise ValueError("INGESTION_DB_URL is not set")
    create_db_if_not_exists(settings.INGESTION_DB_URL)
    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=QDRANT_SCHEMA,
    )

    LOGGER.info(f"Table schema in ingestion : {db_table_schema}")
    LOGGER.info(f"Table name in ingestion : {db_table_name}")

    # Check if source already exists in either database or Qdrant
    if db_service.schema_exists(schema_name=db_table_schema) and db_service.table_exists(
        table_name=db_table_name, schema_name=db_table_schema
    ):
        LOGGER.error(f"Source {source_name} already exists in Database")
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        raise ValueError(
            f"Source '{source_name}' already exists in database table '{db_table_schema}.{db_table_name}'"
        )

    if await qdrant_service.collection_exists_async(qdrant_collection_name):
        LOGGER.error(f"Source {source_name} already exists in Qdrant")
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        raise ValueError(f"Source '{source_name}' already exists in Qdrant collection '{qdrant_collection_name}'")

    LOGGER.info("Starting ingestion process")
    files_info = folder_manager.list_all_files_info()
    if save_supabase:
        files_info = sync_files_to_supabase(
            organization_id=organization_id,
            source_name=source_name,
            get_file_content_func=folder_manager.get_file_content,
            list_of_documents=files_info,
        )
    try:
        document_chunk_mapping = document_chunking_mapping(
            vision_ingestion_service=vision_completion_service,
            llm_service=fallback_vision_llm_service,
            get_file_content_func=folder_manager.get_file_content,
            chunk_size=chunk_size,
            use_llm_for_pdf=settings.USE_LLM_FOR_PDF_PARSING,
            overlapping_size=chunk_overlap,
        )
    except Exception as e:
        LOGGER.error(f"Failed to chunk documents: {str(e)}")
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        return

    document_summary_func = None
    add_summary_in_chunks_func = None
    # TODO: add summary in chunks when we have a full functinality of gemini
    # if add_doc_description_to_chunks:
    #     document_summary_func = partial(
    #         get_summary_from_document,
    #         llm_google_service=GOOGLE_COMPLETION_SERVICE,
    #         get_file_content_func=folder_manager.get_file_content,
    #     )
    #     add_summary_in_chunks_func = add_summary_in_chunks
    db_service.create_schema(db_table_schema)
    LOGGER.info(f"Found {len(files_info)} files to ingest")
    try:
        if len(files_info) == 0:
            LOGGER.warning(f"No files found to ingest in source '{source_name}' - marking as completed")
            LOGGER.info(f"[EMPTY_FOLDER] About to update task status to COMPLETED for task {task_id}")
            # Update task status to COMPLETED for empty folders
            ingestion_task_completed = IngestionTaskUpdate(
                id=task_id,
                source_name=source_name,
                source_type=source_type,
                status=db.TaskStatus.COMPLETED,
            )
            LOGGER.info(f"[EMPTY_FOLDER] Calling update_ingestion_task with status: {ingestion_task_completed.status}")
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=ingestion_task_completed,
            )
            LOGGER.info("[EMPTY_FOLDER] Task status update completed")
            # Still create the empty source in the database for consistency
            LOGGER.info("[EMPTY_FOLDER] About to create empty source in database")
            source_data = DataSourceSchema(
                name=source_name,
                type=source_type,
                database_schema=db_table_schema,
                database_table_name=db_table_name,
                qdrant_collection_name=qdrant_collection_name,
                qdrant_schema=QDRANT_SCHEMA.to_dict(),
                embedding_model_reference=f"{embedding_service._provider}:{embedding_service._model_name}",
                attributes=None,
            )
            LOGGER.info("[EMPTY_FOLDER] Calling create_source for empty folder")
            create_source(
                organization_id=organization_id,
                source_data=source_data,
            )
            LOGGER.info("[EMPTY_FOLDER] Empty source created successfully - returning")
            return
        for document in files_info:
            chunks_df = await get_chunks_dataframe_from_doc(
                document,
                document_chunk_mapping,
                llm_service=fallback_vision_llm_service,
                add_doc_description_to_chunks=add_doc_description_to_chunks,
                documents_summary_func=document_summary_func,
                add_summary_in_chunks_func=add_summary_in_chunks_func,
                default_chunk_size=chunk_size,
            )
            LOGGER.info(f"Sync chunks to db table {db_table_name}")
            db_service.update_table(
                new_df=chunks_df,
                table_name=db_table_name,
                table_definition=FILE_TABLE_DEFINITION,
                id_column_name=ID_COLUMN_NAME,
                timestamp_column_name=TIMESTAMP_COLUMN_NAME,
                append_mode=True,
                schema_name=db_table_schema,
            )
            await sync_chunks_to_qdrant(
                db_table_schema, db_table_name, qdrant_collection_name, db_service, qdrant_service
            )
    except Exception as e:
        LOGGER.error(f"Failed to ingest folder source: {str(e)}")
        ingestion_task.status = db.TaskStatus.FAILED
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        raise  # Re-raise the exception to ensure subprocess exits with non-zero code
    source_data = DataSourceSchema(
        name=source_name,
        type=source_type,
        database_schema=db_table_schema,
        database_table_name=db_table_name,
        qdrant_collection_name=qdrant_collection_name,
        qdrant_schema=QDRANT_SCHEMA.to_dict(),
        embedding_model_reference=f"{embedding_service._provider}:{embedding_service._model_name}",
    )
    LOGGER.info(f"Creating source {source_name} for organization {organization_id} in database")
    source_id = create_source(
        organization_id=organization_id,
        source_data=source_data,
    )

    ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_id=source_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.COMPLETED,
    )

    LOGGER.info(f" Update status {source_name} source for organization {organization_id} in database")
    update_ingestion_task(
        organization_id=organization_id,
        ingestion_task=ingestion_task,
    )
    LOGGER.info(f"Successfully ingested {source_name} source for organization {organization_id}")
