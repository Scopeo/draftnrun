import logging
from pathlib import Path
from typing import Callable

from supabase import Client, create_client

from data_ingestion.document.folder_management.folder_management import FileDocument
from data_ingestion.utils import sanitize_filename
from settings import settings

LOGGER = logging.getLogger(__name__)


def upload_file_to_supabase(
    file_content: bytes,
    supabase_client: Client,
    supabase_url: str,
):
    """Upload a file to supabase"""
    try:
        supabase_client.storage.from_(settings.SUPABASE_BUCKET_NAME).upload(
            file=file_content, path=supabase_url, file_options={"cache-control": "3600", "upsert": "true"}
        )
    except Exception as e:
        LOGGER.error(f"Error uploading file to supabase: {e}")


def get_supabase_url_for_file(
    path_to_file: str,
    organization_id: str,
    source_name: str,
):
    """Get the supabase url for a file"""
    proper_path = Path(path_to_file)
    bucket_name = f"{organization_id}/{source_name}/{proper_path}"
    return sanitize_filename(bucket_name)


def sync_files_to_supabase(
    organization_id: str,
    source_name: str,
    get_file_content_func: Callable,
    list_of_documents: list[FileDocument],
) -> list[FileDocument]:
    LOGGER.info(f"Syncing files to supabase for {organization_id} organization")
    supabase_client = create_client(settings.SUPABASE_PROJECT_URL, settings.SUPABASE_SERVICE_ROLE_SECRET_KEY)

    for doc in list_of_documents:
        doc.metadata["supabase_url"] = get_supabase_url_for_file(
            f"{doc.folder_name}/{doc.file_name}",
            organization_id=organization_id,
            source_name=source_name,
        )
        upload_file_to_supabase(get_file_content_func(doc.id), supabase_client, doc.metadata["supabase_url"])
    return list_of_documents
