import asyncio
import logging
from typing import Optional
from uuid import UUID

from ada_backend.database import models as db
from ada_backend.database.models import SourceType
from ada_backend.database.setup_db import SessionLocal
from ada_backend.schemas.ingestion_task_schema import IngestionTaskUpdate, ResultType, TaskResultMetadata
from ada_backend.services.agent_runner_service import get_organization_llm_providers
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from ingestion_script.ingest_folder_source import ingest_google_drive_source, ingest_local_folder_source
from ingestion_script.ingest_website_source import ingest_website_source
from ingestion_script.utils import update_ingestion_task
from settings import settings

# Configure logging to ensure all logs are captured by worker subprocess
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # Output to stdout for worker to capture
)

LOGGER = logging.getLogger(__name__)
DEFAULT_CHUNK_SIZE = 1024
DEFAULT_CHUNK_OVERLAP = 0
DEFAULT_UPDATE_EXISTING = False


def check_missing_params(
    source_attributes: dict, required_params: list, organization_id: UUID, ingestion_task: IngestionTaskUpdate
) -> bool:
    missing_params = [
        param for param in required_params if param not in source_attributes or not source_attributes[param]
    ]
    if missing_params:
        error_msg = f"Missing required parameters: {', '.join(missing_params)}"
        LOGGER.error(error_msg)
        ingestion_task.result_metadata = TaskResultMetadata(
            message=error_msg,
            type=ResultType.ERROR,
        )
        update_ingestion_task(
            organization_id=organization_id,
            ingestion_task=ingestion_task,
        )
        return True
    return False


async def ingestion_main_async(
    source_name: str,
    organization_id: UUID,
    task_id: UUID,
    source_type: SourceType,
    source_attributes: dict,
    source_id: Optional[UUID] = None,
):
    LOGGER.info(
        f"[INGESTION_MAIN] Starting ingestion - Source: '{source_name}', Type: {source_type}, "
        f"Organization: {organization_id}, Task: {task_id}"
    )

    set_trace_manager(TraceManager(project_name="Ingestion"))
    session = SessionLocal()
    try:
        organization_llm_providers = get_organization_llm_providers(session=session, organization_id=organization_id)
    finally:
        session.close()

    set_tracing_span(
        project_id="None",
        organization_id=organization_id,
        organization_llm_providers=organization_llm_providers,
    )
    LOGGER.info(f"[INGESTION_MAIN] Trace manager and span initialized for task {task_id}")
    chunk_size = source_attributes.get("chunk_size")
    if chunk_size is None:
        chunk_size = DEFAULT_CHUNK_SIZE
    chunk_overlap = source_attributes.get("chunk_overlap")
    if chunk_overlap is None:
        chunk_overlap = DEFAULT_CHUNK_OVERLAP
    update_existing = source_attributes.get("update_existing")
    if update_existing is None:
        update_existing = DEFAULT_UPDATE_EXISTING
    pdf_reading_mode = source_attributes.get("pdf_reading_mode")

    failed_ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.FAILED,
        source_id=source_id,
    )
    LOGGER.debug(f"Starting ingestion for source: {source_name}, type: {source_type}, organization: {organization_id}")
    if source_type == SourceType.GOOGLE_DRIVE:
        if check_missing_params(
            source_attributes=source_attributes,
            required_params=["access_token", "folder_id"],
            organization_id=organization_id,
            ingestion_task=failed_ingestion_task,
        ):
            return
        access_token = source_attributes.get("access_token")
        folder_id = source_attributes.get("folder_id")
        if folder_id == "/":
            LOGGER.warning(
                "Google Drive folder_id should be a specific ID, not just '/'",
            )
        try:
            await ingest_google_drive_source(
                folder_id=folder_id,
                organization_id=organization_id,
                source_name=source_name,
                task_id=task_id,
                save_supabase=True,
                access_token=access_token,
                add_doc_description_to_chunks=False,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                source_id=source_id,
                pdf_reading_mode=pdf_reading_mode,
                llamaparse_api_key=settings.LLAMACLOUD_API_KEY,
            )
        except Exception as e:
            error_msg = f"Error during google drive ingestion: {str(e)}"
            LOGGER.error(error_msg)
            failed_ingestion_task.result_metadata = TaskResultMetadata(
                message=error_msg,
                type=ResultType.ERROR,
            )
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            raise  # Re-raise the exception to ensure subprocess exits with non-zero code

    elif source_type == SourceType.LOCAL:
        if check_missing_params(
            source_attributes=source_attributes,
            required_params=["list_of_files_from_local_folder"],
            organization_id=organization_id,
            ingestion_task=failed_ingestion_task,
        ):
            return

        try:
            await ingest_local_folder_source(
                list_of_files_to_ingest=source_attributes["list_of_files_from_local_folder"],
                organization_id=organization_id,
                source_name=source_name,
                task_id=task_id,
                save_supabase=True,
                add_doc_description_to_chunks=False,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                source_id=source_id,
                pdf_reading_mode=pdf_reading_mode,
                llamaparse_api_key=settings.LLAMACLOUD_API_KEY,
            )
        except Exception as e:
            error_msg = f"Error during local ingestion: {str(e)}"
            LOGGER.error(error_msg)
            failed_ingestion_task.result_metadata = TaskResultMetadata(
                message=error_msg,
                type=ResultType.ERROR,
            )
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            raise  # Re-raise the exception to ensure subprocess exits with non-zero code

    elif source_type == SourceType.DATABASE:
        if check_missing_params(
            source_attributes=source_attributes,
            required_params=[
                "source_db_url",
                "source_table_name",
                "id_column_name",
                "text_column_names",
            ],
            organization_id=organization_id,
            ingestion_task=failed_ingestion_task,
        ):
            return

        from ingestion_script.ingest_db_source import ingestion_database

        try:
            await ingestion_database(
                source_name=source_name,
                organization_id=organization_id,
                task_id=task_id,
                source_db_url=source_attributes["source_db_url"],
                source_table_name=source_attributes["source_table_name"],
                id_column_name=source_attributes["id_column_name"],
                text_column_names=source_attributes["text_column_names"],
                source_schema_name=source_attributes.get("source_schema_name"),
                metadata_column_names=source_attributes.get("metadata_column_names"),
                timestamp_column_name=source_attributes.get("timestamp_column_name"),
                url_pattern=source_attributes.get("url_pattern"),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                update_existing=update_existing,
                query_filter=source_attributes.get("query_filter"),
                timestamp_filter=source_attributes.get("timestamp_filter"),
                source_attributes=source_attributes,
                source_id=source_id,
            )
        except Exception as e:
            error_msg = f"Error during database ingestion: {str(e)}"
            LOGGER.error(error_msg)
            failed_ingestion_task.result_metadata = TaskResultMetadata(
                message=error_msg,
                type=ResultType.ERROR,
            )
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            raise  # Re-raise the exception to ensure subprocess exits with non-zero code

    elif source_type == SourceType.WEBSITE:
        if not source_attributes.get("url"):
            error_msg = "URL must be provided for website ingestion"
            LOGGER.error(error_msg)
            failed_ingestion_task.result_metadata = TaskResultMetadata(
                message=error_msg,
                type=ResultType.ERROR,
            )
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            return

        if not settings.FIRECRAWL_API_KEY:
            error_msg = "FIRECRAWL_API_KEY is not set. Please configure it in your settings."
            LOGGER.error(error_msg)
            failed_ingestion_task.result_metadata = TaskResultMetadata(
                message=error_msg,
                type=ResultType.ERROR,
            )
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            raise ValueError("FIRECRAWL_API_KEY is required for website ingestion. Please set it in your settings.")

        try:
            await ingest_website_source(
                url=source_attributes.get("url"),
                organization_id=organization_id,
                source_name=source_name,
                task_id=task_id,
                follow_links=source_attributes.get("follow_links", True),
                max_depth=source_attributes.get("max_depth", 1),
                limit=source_attributes.get("limit", 100),
                include_paths=source_attributes.get("include_paths"),
                exclude_paths=source_attributes.get("exclude_paths"),
                include_tags=source_attributes.get("include_tags"),
                exclude_tags=source_attributes.get("exclude_tags"),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                source_id=source_id,
            )
        except Exception as e:
            error_msg = f"Error during website ingestion: {str(e)}"
            LOGGER.error(error_msg)
            failed_ingestion_task.result_metadata = TaskResultMetadata(
                message=error_msg,
                type=ResultType.ERROR,
            )
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            raise  # Re-raise the exception to ensure subprocess exits with non-zero code


def ingestion_main(**kwargs):
    LOGGER.info(f"[INGESTION_MAIN] Entry point called with kwargs: {list(kwargs.keys())}")
    try:
        asyncio.run(ingestion_main_async(**kwargs))
        LOGGER.info("[INGESTION_MAIN] Completed successfully")
    except Exception as e:
        LOGGER.error(f"[INGESTION_MAIN] FAILED with error: {str(e)}")
        raise
