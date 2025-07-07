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
from ingestion_script.utils import create_source, get_sanitize_names, update_ingestion_task
from settings import settings

LOGGER = logging.getLogger(__name__)

# TODO: add the selection at the user level
if (settings.custom_llm_models is not None) and (len(settings.custom_llm_models) > 0):
    llm_model_provider = list(settings.custom_llm_models.keys())[0]
    llm_base_url = settings.custom_llm_models[llm_model_provider]["base_url"]
    llm_api_key = settings.custom_llm_models[llm_model_provider]["api_key"]
    llm_model_name = settings.custom_llm_models[llm_model_provider]["model_name"][0]
    VISION_COMPLETION_SERVICE = VisionService(
        trace_manager=TraceManager(project_name="ingestion"),
        provider=llm_model_provider,
        model_name=llm_model_name,
        api_key=llm_api_key,
        base_url=llm_base_url,
        temperature=0.0,
    )
    FALLBACK_VISION_LLM_SERVICE = VISION_COMPLETION_SERVICE
else:
    VISION_COMPLETION_SERVICE = VisionService(
        provider="google",
        model_name="gemini-2.0-flash-exp",
        trace_manager=TraceManager(project_name="ingestion"),
    )
    FALLBACK_VISION_LLM_SERVICE = VisionService(
        provider="openai",
        model_name="gpt-4.1-mini",
        trace_manager=TraceManager(project_name="ingestion"),
    )

# TODO: add the selection at the user level
if (settings.custom_embedding_models is not None) and (len(settings.custom_embedding_models) > 0):
    embedding_model_provider = list(settings.custom_embedding_models.keys())[0]
    embedding_base_url = settings.custom_embedding_models[embedding_model_provider]["base_url"]
    embedding_api_key = settings.custom_embedding_models[embedding_model_provider]["api_key"]
    embedding_model_name = settings.custom_embedding_models[embedding_model_provider]["model_name"][0]
    embedding_model_embedding_size = settings.custom_embedding_models[embedding_model_provider]["embedding_size"][
        embedding_model_name
    ]
    EMBEDDING_SERVICE = EmbeddingService(
        provider=embedding_model_provider,
        model_name=embedding_model_name,
        trace_manager=TraceManager(project_name="ingestion"),
        api_key=embedding_api_key,
        base_url=embedding_base_url,
        embedding_size=embedding_model_embedding_size,
    )
else:
    EMBEDDING_SERVICE = EmbeddingService(
        provider="openai",
        model_name="text-embedding-3-large",
        trace_manager=TraceManager(project_name="ingestion"),
    )

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
) -> None:
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
    )


async def ingest_local_folder_source(
    list_of_files_to_ingest: list[dict],
    organization_id: str,
    source_name: str,
    task_id: UUID,
    save_supabase: bool = True,
    add_doc_description_to_chunks: bool = False,
    chunk_size: Optional[int] = 1024,
) -> None:
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
) -> None:
    db_table_schema, db_table_name, qdrant_collection_name = get_sanitize_names(
        source_name=source_name,
        organization_id=organization_id,
    )

    if settings.INGESTION_DB_URL is None:
        raise ValueError("INGESTION_DB_URL is not set")
    create_db_if_not_exists(settings.INGESTION_DB_URL)
    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    qdrant_service = QdrantService.from_defaults(
        embedding_service=EMBEDDING_SERVICE,
        default_collection_schema=QDRANT_SCHEMA,
    )

    LOGGER.info(f"Table schema in ingestion : {db_table_schema}")
    LOGGER.info(f"Table name in ingestion : {db_table_name}")

    ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.FAILED,
    )

    # Check if source already exists in either database or Qdrant
    if db_service.schema_exists(schema_name=db_table_schema) and db_service.table_exists(
        table_name=db_table_name, schema_name=db_table_schema
    ):
        LOGGER.error(f"Source {source_name} already exists in Database")
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        return

    if await qdrant_service.collection_exists_async(qdrant_collection_name):
        LOGGER.error(f"Source {source_name} already exists in Qdrant")
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        return

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
            vision_ingestion_service=VISION_COMPLETION_SERVICE,
            llm_service=FALLBACK_VISION_LLM_SERVICE,
            get_file_content_func=folder_manager.get_file_content,
            chunk_size=chunk_size,
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
            raise ValueError("No files found to ingest")
        for document in files_info:
            chunks_df = await get_chunks_dataframe_from_doc(
                document,
                document_chunk_mapping,
                llm_service=FALLBACK_VISION_LLM_SERVICE,
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
        return
    source_data = DataSourceSchema(
        name=source_name,
        type=source_type,
        database_schema=db_table_schema,
        database_table_name=db_table_name,
        qdrant_collection_name=qdrant_collection_name,
        qdrant_schema=QDRANT_SCHEMA.to_dict(),
        embedding_model_reference=f"{EMBEDDING_SERVICE._provider}:{EMBEDDING_SERVICE._model_name}",
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
