import logging
from uuid import UUID

from ada_backend.database.models import SourceType
from ada_backend.schemas.ingestion_task_schema import IngestionTaskUpdate
from ingestion_script.ingest_folder_source import ingest_google_drive_source, ingest_local_folder_source
from ingestion_script.utils import update_ingestion_task
from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


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


def ingestion_main(
    source_name: str, organization_id: UUID, task_id: UUID, source_type: SourceType, source_attributes: dict
):
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
            ingest_google_drive_source(
                folder_id=folder_id,
                organization_id=organization_id,
                source_name=source_name,
                task_id=task_id,
                save_supabase=True,
                access_token=access_token,
                add_doc_description_to_chunks=False,
            )
        except Exception as e:
            LOGGER.error(f"Error during google drive ingestion: {str(e)}")
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            return

    elif source_type == SourceType.LOCAL:
        if check_missing_params(
            source_attributes=source_attributes,
            required_params=["path"],
            organization_id=organization_id,
            ingestion_task=failed_ingestion_task,
        ):
            return

        try:
            ingest_local_folder_source(
                path=source_attributes["path"],
                organization_id=organization_id,
                source_name=source_name,
                task_id=task_id,
                save_supabase=True,
                add_doc_description_to_chunks=False,
            )
        except Exception as e:
            LOGGER.error(f"Error during local ingestion: {str(e)}")
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            return

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
            ingestion_database(
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
                is_sync_enabled=source_attributes.get("is_sync_enabled", False),
            )
        except Exception as e:
            LOGGER.error(f"Error during database ingestion: {str(e)}")
            update_ingestion_task(
                organization_id=organization_id,
                ingestion_task=failed_ingestion_task,
            )
            return
