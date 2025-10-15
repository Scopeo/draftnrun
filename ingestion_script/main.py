import asyncio
import logging
from typing import Optional
from uuid import UUID

from ada_backend.database.models import SourceType
from ada_backend.database.setup_db import SessionLocal
from ada_backend.schemas.ingestion_task_schema import IngestionTaskUpdate
from ada_backend.services.agent_runner_service import get_organization_llm_providers
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from ingestion_script.ingest_folder_source import ingest_google_drive_source, ingest_local_folder_source
from ingestion_script.utils import update_ingestion_task
from ada_backend.database import models as db

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
        LOGGER.error(f"Missing required parameters: {', '.join(missing_params)}")
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
    source_id: Optional[str] = None,
):
    LOGGER.info(f"[INGESTION_MAIN] Starting ingestion - Source: '{source_name}', Type: {source_type}, Organization: {organization_id}, Task: {task_id}")

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

    failed_ingestion_task = IngestionTaskUpdate(
        id=task_id,
        source_name=source_name,
        source_type=source_type,
        status=db.TaskStatus.FAILED,
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
            )
        except Exception as e:
            LOGGER.error(f"Error during google drive ingestion: {str(e)}")
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
            )
        except Exception as e:
            LOGGER.error(f"Error during local ingestion: {str(e)}")
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
            LOGGER.error(f"Error during database ingestion: {str(e)}")
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            raise  # Re-raise the exception to ensure subprocess exits with non-zero code


def ingestion_main(**kwargs):
    LOGGER.info(f"[INGESTION_MAIN] Entry point called with kwargs: {list(kwargs.keys())}")
    try:
        asyncio.run(ingestion_main_async(**kwargs))
        LOGGER.info(f"[INGESTION_MAIN] Completed successfully")
    except Exception as e:
        LOGGER.error(f"[INGESTION_MAIN] FAILED with error: {str(e)}")
        raise
