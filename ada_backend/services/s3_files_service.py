import logging

from ada_backend.schemas.ingestion_task_schema import (
    S3UploadedInformation,
)
from data_ingestion.boto3_client import (
    get_s3_boto3_client,
    upload_file_to_bucket,
    sanitize_s3_key,
    delete_file_from_bucket,
    is_bucket_existing,
    create_bucket,
)
from settings import settings

LOGGER = logging.getLogger(__name__)

S3_CLIENT = get_s3_boto3_client()
if not is_bucket_existing(s3_client=S3_CLIENT, bucket_name=settings.S3_BUCKET_NAME):
    LOGGER.warning(f"Bucket {settings.S3_BUCKET_NAME} does not exist.Creating it.")
    create_bucket(s3_client=S3_CLIENT, bucket_name=settings.S3_BUCKET_NAME)


def upload_file_to_s3(
    file_name: str,
    byte_content: bytes,
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> S3UploadedInformation:
    """Upload a file to an S3 bucket."""
    sanitized_key = sanitize_s3_key(file_name)
    try:
        upload_file_to_bucket(
            s3_client=S3_CLIENT, bucket_name=bucket_name, key=sanitized_key, byte_content=byte_content
        )
        LOGGER.info(f"Successfully uploaded file to S3 with {sanitized_key} key.")
        return S3UploadedInformation(s3_sanitized_name=sanitized_key)
    except Exception as e:
        LOGGER.error(f"Error uploading file to S3: {str(e)}")
        raise ValueError(f"Failed to upload file to S3: {str(e)}")


def delete_file_from_s3(
    key: str,
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> None:
    try:
        delete_file_from_bucket(s3_client=S3_CLIENT, bucket_name=bucket_name, key=key)
        LOGGER.info(f"Successfully deleted file from S3 with {key} key.")
    except Exception as e:
        LOGGER.error(f"Error deleting file from S3: {str(e)}")
        raise ValueError(f"Failed to delete file from S3: {str(e)}")
