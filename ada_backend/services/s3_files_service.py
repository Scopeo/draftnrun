import logging
from functools import lru_cache

import boto3

from ada_backend.schemas.ingestion_task_schema import (
    S3UploadedInformation,
)
from data_ingestion.boto3_client import (
    get_s3_boto3_client,
    upload_file_to_bucket,
    delete_file_from_bucket,
    is_bucket_existing,
    create_bucket,
)
from data_ingestion.utils import sanitize_filename
from settings import settings

LOGGER = logging.getLogger(__name__)


@lru_cache()
def get_s3_client_and_ensure_bucket() -> boto3.client:
    """
    Lazily create the S3 client and ensure the bucket exists.
    """
    s3_client = get_s3_boto3_client()
    if settings.S3_BUCKET_NAME is None:
        raise ValueError(
            "S3_BUCKET_NAME (bucket to store files for ingestion) is not configured in settings."
            " Please set it in the credentials.env file."
        )

    if not is_bucket_existing(s3_client=s3_client, bucket_name=settings.S3_BUCKET_NAME):
        LOGGER.warning(f"Bucket {settings.S3_BUCKET_NAME} does not exist. Creating it.")
        create_bucket(s3_client=s3_client, bucket_name=settings.S3_BUCKET_NAME)

    return s3_client


def upload_file_to_s3(
    file_name: str,
    byte_content: bytes,
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> S3UploadedInformation:
    """Upload a file to an S3 bucket."""
    sanitized_key = sanitize_filename(file_name, remove_extension_dot=False)
    try:
        s3_client = get_s3_client_and_ensure_bucket()
        upload_file_to_bucket(
            s3_client=s3_client, bucket_name=bucket_name, key=sanitized_key, byte_content=byte_content
        )
        LOGGER.info(f"Successfully uploaded file to S3 with {sanitized_key} key.")
        return S3UploadedInformation(s3_path_file=sanitized_key)
    except Exception as e:
        LOGGER.error(f"Error uploading file to S3: {str(e)}")
        raise ValueError(f"Failed to upload file to S3: {str(e)}")


def delete_file_from_s3(
    key: str,
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> None:
    try:
        s3_client = get_s3_client_and_ensure_bucket()
        delete_file_from_bucket(s3_client=s3_client, bucket_name=bucket_name, key=key)
        LOGGER.info(f"Successfully deleted file from S3 with {key} key.")
    except Exception as e:
        LOGGER.error(f"Error deleting file from S3: {str(e)}")
        raise ValueError(f"Failed to delete file from S3: {str(e)}")
