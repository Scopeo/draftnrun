import base64
import logging
import mimetypes
from pathlib import Path
from typing import List, Optional

from ada_backend.database.models import ResponseFormat
from ada_backend.schemas.project_schema import FileResponse
from ada_backend.services.s3_files_service import (
    generate_presigned_download_url,
    get_s3_client_and_ensure_bucket,
)
from data_ingestion.boto3_client import upload_file_to_bucket
from data_ingestion.utils import sanitize_filename
from settings import settings

LOGGER = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_FILES_FOR_BASE64 = 5
WHITELISTED_FILE_EXTENSIONS = [
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tiff",
    ".pdf",
    ".docx",
    ".xlsx",
    ".csv",
    ".txt",
    ".md",
    ".json",
    ".html",
    ".xml",
]


def temp_folder_exists(temp_folder_path: str) -> bool:
    temp_folder = Path(temp_folder_path)
    return temp_folder.is_dir()


def get_mime_type(file_path: Path) -> str:
    """Determine MIME type from file extension."""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type or "application/octet-stream"


def collect_file_paths_from_temp_folder(temp_folder_path: str) -> List[Path]:
    """
    Recursively collect all OUTPUT files from the temporary folder.
    Excludes hidden files, directories, and the 'input/' subfolder.
    Returns sorted list of file paths.
    """
    if not temp_folder_exists(temp_folder_path):
        LOGGER.debug(f"Temp folder does not exist or is not a directory: {temp_folder_path}")
        return []

    temp_folder = Path(temp_folder_path)
    input_folder = temp_folder / "input"

    file_paths = []
    try:
        for item in temp_folder.rglob("*"):
            if input_folder in item.parents or item == input_folder:
                continue

            if item.is_file() and not item.name.startswith(".") and item.suffix.lower() in WHITELISTED_FILE_EXTENSIONS:
                file_paths.append(item)
    except Exception as e:
        LOGGER.error(f"Error collecting files from temp folder {temp_folder_path}: {str(e)}", exc_info=True)
        return []

    file_paths.sort(key=lambda p: str(p))
    return file_paths


def convert_file_to_base64(file_path: Path, max_size: int = MAX_FILE_SIZE_BYTES) -> Optional[str]:
    try:
        file_size = file_path.stat().st_size
        if file_size > max_size:
            LOGGER.warning(
                f"File {file_path.name} exceeds size limit ({file_size} bytes > {max_size} bytes). Skipping."
            )
            return None

        with open(file_path, "rb") as f:
            file_bytes = f.read()
        base64_data = base64.b64encode(file_bytes).decode("utf-8")
        return base64_data
    except Exception as e:
        LOGGER.error(f"Error converting file {file_path} to base64: {str(e)}", exc_info=True)
        return None


def upload_file_to_s3_and_get_url(
    file_path: Path, org_id: str, project_id: str, conversation_id: str, max_size: int = MAX_FILE_SIZE_BYTES
) -> Optional[tuple[str, str]]:
    try:
        file_size = file_path.stat().st_size
        if file_size > max_size:
            LOGGER.warning(
                f"File {file_path.name} exceeds size limit ({file_size} bytes > {max_size} bytes). Skipping."
            )
            return None

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        sanitized_filename = sanitize_filename(file_path.name, remove_extension_dot=False)
        s3_key = f"temp-files/{org_id}/{project_id}/{conversation_id}/{sanitized_filename}"

        playground_bucket_name = settings.PLAYGROUND_S3_BUCKET_NAME
        if playground_bucket_name is None:
            LOGGER.error(
                "Playground bucket name is not configured in settings. Please set it in the credentials.env file."
            )
            return None
        s3_client = get_s3_client_and_ensure_bucket(bucket_name=playground_bucket_name)
        upload_file_to_bucket(
            s3_client=s3_client,
            bucket_name=playground_bucket_name,
            key=s3_key,
            byte_content=file_bytes,
        )

        presigned_url = generate_presigned_download_url(
            s3_client=s3_client,
            key=s3_key,
            expiration=3600,
            bucket_name=playground_bucket_name,
        )

        return presigned_url, s3_key
    except Exception as e:
        LOGGER.error(f"Error uploading file {file_path} to S3: {str(e)}", exc_info=True)
        return None


def process_files_for_response(
    temp_folder_path: str,
    org_id: str,
    project_id: str,
    conversation_id: str,
    response_format: Optional[ResponseFormat],
) -> List[FileResponse]:
    """
    Process all files from the temp folder based on response_format.
    """
    if response_format is None:
        return []

    file_paths = collect_file_paths_from_temp_folder(temp_folder_path)
    if not file_paths:
        LOGGER.debug(f"No files found in temp folder: {temp_folder_path}")
        return []

    file_responses = []
    base64_file_count = 0

    for file_path in file_paths:
        try:
            file_size = file_path.stat().st_size
            if file_size > MAX_FILE_SIZE_BYTES:
                LOGGER.warning(
                    f"Skipping file {file_path.name} - exceeds size limit "
                    f"({file_size} bytes > {MAX_FILE_SIZE_BYTES} bytes)"
                )
                continue

            content_type = get_mime_type(file_path)

            if response_format == ResponseFormat.BASE64:
                if base64_file_count >= MAX_FILES_FOR_BASE64:
                    LOGGER.warning(
                        f"Skipping file {file_path.name} - reached max base64 files ({MAX_FILES_FOR_BASE64})"
                    )
                    continue

                base64_data = convert_file_to_base64(file_path)
                if base64_data is not None:
                    file_responses.append(
                        FileResponse(
                            filename=file_path.name,
                            content_type=content_type,
                            size=file_size,
                            data=base64_data,
                            url=None,
                        )
                    )
                    base64_file_count += 1
            elif response_format == ResponseFormat.URL:
                result = upload_file_to_s3_and_get_url(file_path, org_id, project_id, conversation_id)
                if result is not None:
                    presigned_url, s3_key = result
                    file_responses.append(
                        FileResponse(
                            filename=file_path.name,
                            content_type=content_type,
                            size=file_size,
                            data=None,
                            url=presigned_url,
                            s3_key=None,
                        )
                    )
            elif response_format == ResponseFormat.S3_KEY:
                result = upload_file_to_s3_and_get_url(file_path, org_id, project_id, conversation_id)
                if result is not None:
                    presigned_url, s3_key = result
                    file_responses.append(
                        FileResponse(
                            filename=file_path.name,
                            content_type=content_type,
                            size=file_size,
                            data=None,
                            url=None,
                            s3_key=s3_key,
                        )
                    )
            else:
                LOGGER.warning(f"Unsupported response format: {response_format}")
                continue
        except Exception as e:
            LOGGER.error(f"Error processing file {file_path}: {str(e)}", exc_info=True)
            continue

    return file_responses
