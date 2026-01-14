import logging
import uuid
from typing import Optional
from uuid import UUID

import pandas as pd

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import IngestionTaskUpdate, ResultType, TaskResultMetadata
from ada_backend.schemas.source_schema import DataSourceSchema
from data_ingestion.document.document_chunking import document_chunking_mapping, get_chunks_dataframe_from_doc
from data_ingestion.document.folder_management.folder_management import FolderManager
from data_ingestion.document.folder_management.google_drive_folder_management import GoogleDriveFolderManager
from data_ingestion.document.folder_management.s3_folder_management import S3FolderManager
from data_ingestion.document.supabase_file_uploader import sync_files_to_supabase
from data_ingestion.utils import PDFReadingMode
from engine.llm_services.llm_service import EmbeddingService, VisionService
from engine.qdrant_service import FieldSchema, QdrantService
from engine.storage_service.db_service import DBService
from engine.storage_service.db_utils import create_db_if_not_exists
from engine.storage_service.local_service import SQLLocalService
from engine.trace.trace_manager import TraceManager
from ingestion_script.folder_utils import prepare_df_for_qdrant, sanitize_for_json
from ingestion_script.utils import (
    CHUNK_ID_COLUMN_NAME,
    SOURCE_ID_COLUMN_NAME,
    TIMESTAMP_COLUMN_NAME,
    UNIFIED_QDRANT_SCHEMA,
    UNIFIED_TABLE_DEFINITION,
    create_source,
    get_first_available_embeddings_custom_llm,
    get_first_available_multimodal_custom_llm,
    get_sanitize_names,
    transform_chunks_df_for_unified_table,
    update_ingestion_task,
)
from settings import settings

LOGGER = logging.getLogger(__name__)


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
    source_id: Optional[str] = None,
) -> None:
    if source_id and sql_query_filter:
        combined_filter = f"({sql_query_filter}) AND {SOURCE_ID_COLUMN_NAME} = '{source_id}'"
    elif source_id:
        combined_filter = f"{SOURCE_ID_COLUMN_NAME} = '{source_id}'"
    else:
        combined_filter = sql_query_filter

    chunks_df = db_service.get_table_df(
        table_name,
        schema_name=table_schema,
        sql_query_filter=combined_filter,
    )
    LOGGER.info(
        f"Found {len(chunks_df)} chunks to sync to Qdrant from table {table_name} "
        f"in schema {table_schema} with filter {combined_filter}"
    )

    chunks_df = prepare_df_for_qdrant(chunks_df)

    if source_id:
        source_id_filter = {"key": SOURCE_ID_COLUMN_NAME, "match": {"value": str(source_id)}}
        combined_filter_qdrant = qdrant_service._combine_filters(
            base_filter=query_filter_qdrant,
            additional_filters=[source_id_filter],
        )
    else:
        combined_filter_qdrant = query_filter_qdrant

    LOGGER.info(f"Syncing chunks to Qdrant collection {collection_name} with {len(chunks_df)} rows")
    if not await qdrant_service.collection_exists_async(collection_name):
        await qdrant_service.create_collection_async(collection_name)
        await qdrant_service.create_index_if_needed_async(collection_name, SOURCE_ID_COLUMN_NAME, FieldSchema.KEYWORD)
        await qdrant_service.create_index_if_needed_async(collection_name, CHUNK_ID_COLUMN_NAME, FieldSchema.KEYWORD)
    await qdrant_service.sync_df_with_collection_async(
        df=chunks_df,
        collection_name=collection_name,
        query_filter_qdrant=combined_filter_qdrant,
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
    source_id: Optional[UUID] = None,
    pdf_reading_mode: PDFReadingMode = PDFReadingMode.STANDARD,
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
        source_id=source_id,
        pdf_reading_mode=pdf_reading_mode,
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
    source_id: Optional[UUID] = None,
    pdf_reading_mode: PDFReadingMode = PDFReadingMode.STANDARD,
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
        source_id=source_id,
        pdf_reading_mode=pdf_reading_mode,
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
    source_id: Optional[UUID] = None,
    pdf_reading_mode: PDFReadingMode = PDFReadingMode.STANDARD,
) -> None:
    if source_id is None:
        source_id = uuid.uuid4()
    ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.FAILED,
        source_id=source_id,
    )
    if settings.USE_LLM_FOR_PDF_PARSING:
        try:
            vision_completion_service, fallback_vision_llm_service = load_llms_services()
        except ValueError as e:
            error_msg = f"Failed to load LLM services: {str(e)}"
            LOGGER.error(error_msg)
            ingestion_task.result_metadata = TaskResultMetadata(
                message=error_msg,
                type=ResultType.ERROR,
            )
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
        error_msg = f"Failed to load embedding service: {str(e)}"
        LOGGER.error(error_msg)
        ingestion_task.result_metadata = TaskResultMetadata(
            message=error_msg,
            type=ResultType.ERROR,
        )
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        return
    embedding_model_ref = f"{embedding_service._provider}:{embedding_service._model_name}"
    db_table_schema, db_table_name, qdrant_collection_name = get_sanitize_names(
        organization_id=organization_id,
        embedding_model_reference=embedding_model_ref,
    )

    LOGGER.info(f"Table schema in ingestion : {db_table_schema}")
    LOGGER.info(f"Table name in ingestion : {db_table_name}")
    source_data = DataSourceSchema(
        id=source_id,
        name=source_name,
        type=source_type,
        database_schema=db_table_schema,
        database_table_name=db_table_name,
        qdrant_collection_name=qdrant_collection_name,
        qdrant_schema=UNIFIED_QDRANT_SCHEMA.to_dict(),
        embedding_model_reference=embedding_model_ref,
    )
    if settings.INGESTION_DB_URL is None:
        raise ValueError("INGESTION_DB_URL is not set")
    create_db_if_not_exists(settings.INGESTION_DB_URL)
    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    qdrant_service = QdrantService.from_defaults(
        embedding_service=embedding_service,
        default_collection_schema=UNIFIED_QDRANT_SCHEMA,
    )

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
            pdf_reading_mode=pdf_reading_mode,
            overlapping_size=chunk_overlap,
        )
    except Exception as e:
        error_msg = f"Failed to chunk documents: {str(e)}, PDF reading mode: {pdf_reading_mode.value}"
        LOGGER.error(error_msg)
        ingestion_task.result_metadata = TaskResultMetadata(
            message=error_msg,
            type=ResultType.ERROR,
        )
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
                source_id=source_id,
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
            LOGGER.info("[EMPTY_FOLDER] Calling create_source for empty folder")
            create_source(
                organization_id=organization_id,
                source_data=source_data,
            )
            LOGGER.info("[EMPTY_FOLDER] Empty source created successfully - returning")
            return

        file_chunks_dfs = []
        failed_files = []
        successful_files = []

        for document in files_info:
            try:
                chunks_df = await get_chunks_dataframe_from_doc(
                    document,
                    document_chunk_mapping,
                    llm_service=fallback_vision_llm_service,
                    add_doc_description_to_chunks=add_doc_description_to_chunks,
                    documents_summary_func=document_summary_func,
                    add_summary_in_chunks_func=add_summary_in_chunks_func,
                    default_chunk_size=chunk_size,
                )

                if chunks_df.empty:
                    LOGGER.warning(f"No chunks created for {document.file_name} - skipping")
                    continue

                file_chunks_dfs.append(chunks_df)
                successful_files.append({"file_name": document.file_name, "chunks_count": len(chunks_df)})
                LOGGER.info(f"Created {len(chunks_df)} chunks for {document.file_name}")
            except Exception as e:
                error_msg = f"Failed to process {document.file_name}: {str(e)}"
                LOGGER.error(error_msg)
                failed_files.append({"file_name": document.file_name, "reason": str(e)})
                continue

        if not file_chunks_dfs:
            LOGGER.warning("No chunks created from any file - marking task as FAILED")
            if failed_files:
                error_messages = []
                for f in failed_files:
                    file_name = f["file_name"]
                    reason = f["reason"]
                    error_messages.append(f"{file_name}: {reason}")
                error_msg = " | ".join(error_messages)
            else:
                error_msg = f"Unable to process files, PDF reading mode: {pdf_reading_mode.value}"

            ingestion_task_failed = IngestionTaskUpdate(
                id=task_id,
                source_id=None,
                source_name=source_name,
                source_type=source_type,
                status=db.TaskStatus.FAILED,
                result_metadata=TaskResultMetadata(
                    message=error_msg,
                    type=ResultType.ERROR,
                ),
            )
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=ingestion_task_failed,
            )
            LOGGER.error("[NO_CHUNKS] Task marked as FAILED - no source created")
            return

        all_chunks_df = pd.concat(file_chunks_dfs, ignore_index=True)

        initial_count = len(all_chunks_df)
        all_chunks_df = all_chunks_df[all_chunks_df["content"].notna() & (all_chunks_df["content"].str.strip() != "")]
        filtered_count = initial_count - len(all_chunks_df)
        if filtered_count > 0:
            LOGGER.info(f"Filtered out {filtered_count} chunks with empty content")

        if all_chunks_df.empty:
            LOGGER.warning("No valid chunks remaining after filtering - nothing to sync")
            return

        if "document_title" in all_chunks_df.columns:
            all_chunks_df["document_title"] = all_chunks_df["document_title"].apply(sanitize_for_json)
        if "metadata" in all_chunks_df.columns:
            all_chunks_df["metadata"] = all_chunks_df["metadata"].apply(sanitize_for_json)
        if "url" in all_chunks_df.columns:
            all_chunks_df["url"] = all_chunks_df["url"].apply(sanitize_for_json)

        all_chunks_df_for_db = transform_chunks_df_for_unified_table(all_chunks_df, source_id)

        LOGGER.info(f"Syncing {len(all_chunks_df_for_db)} total chunks to db table {db_table_name}")
        db_service.update_table(
            new_df=all_chunks_df_for_db,
            table_name=db_table_name,
            table_definition=UNIFIED_TABLE_DEFINITION,
            id_column_name=CHUNK_ID_COLUMN_NAME,
            timestamp_column_name=TIMESTAMP_COLUMN_NAME,
            append_mode=True,
            schema_name=db_table_schema,
            source_id=str(source_id),
        )

        await sync_chunks_to_qdrant(
            table_schema=db_table_schema,
            table_name=db_table_name,
            collection_name=qdrant_collection_name,
            db_service=db_service,
            qdrant_service=qdrant_service,
            source_id=str(source_id),
        )
    except Exception as e:
        error_msg = f"Failed to ingest folder source: {str(e)}, PDF reading mode: {pdf_reading_mode.value}"
        LOGGER.error(error_msg)
        ingestion_task.status = db.TaskStatus.FAILED
        ingestion_task.result_metadata = TaskResultMetadata(
            message=error_msg,
            type=ResultType.ERROR,
        )
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        raise  # Re-raise the exception to ensure subprocess exits with non-zero code

    # Create the source in the database before updating task status
    LOGGER.info(f"Creating source {source_name} for organization {organization_id} in database")
    create_source(
        organization_id=organization_id,
        source_data=source_data,
    )

    if failed_files:
        error_messages = []
        for f in failed_files:
            file_name = f["file_name"]
            reason = f["reason"]
            error_messages.append(f"{file_name}: {reason}")
        failed_files_errors_str = " | ".join(error_messages)
        ingestion_task = IngestionTaskUpdate(
            id=task_id,
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            status=db.TaskStatus.COMPLETED,
            result_metadata=TaskResultMetadata(
                message=(
                    f"Partially completed: {len(successful_files)} succeeded, {len(failed_files)} failed. "
                    f"PDF reading mode: {pdf_reading_mode.value}. "
                    f"Failed files: {failed_files_errors_str}"
                ),
                type=ResultType.PARTIAL_SUCCESS,
            ),
        )
    else:
        ingestion_task = IngestionTaskUpdate(
            id=task_id,
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            status=db.TaskStatus.COMPLETED,
        )

    LOGGER.info(f" Update status {str(source_id)} source for organization {organization_id} in database")
    update_ingestion_task(
        organization_id=organization_id,
        ingestion_task=ingestion_task,
    )

    LOGGER.info(
        f"Successfully ingested {len(files_info)} files to {str(source_id)} source for organization {organization_id}"
    )
