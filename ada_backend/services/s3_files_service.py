import logging
from functools import lru_cache
from uuid import UUID, uuid4

import boto3

from ada_backend.schemas.ingestion_task_schema import (
    S3UploadedInformation,
)
from ada_backend.schemas.s3_file_schema import (
    CompletedPart,
    MultipartInitResponse,
    PresignedPartURL,
    S3UploadURL,
    UploadFileRequest,
)
from data_ingestion.boto3_client import (
    create_bucket,
    delete_file_from_bucket,
    get_s3_boto3_client,
    is_bucket_existing,
    upload_file_to_bucket,
)
from data_ingestion.utils import sanitize_filename
from settings import settings

LOGGER = logging.getLogger(__name__)


def generate_upload_key(organization_id: UUID, filename: str) -> str:
    s3_filename = f"{organization_id}/{uuid4()}_{filename}"
    return sanitize_filename(s3_filename, remove_extension_dot=False)


@lru_cache()
def get_s3_client_and_ensure_bucket(bucket_name: str) -> boto3.client:
    """
    Lazily create the S3 client and ensure the bucket exists.
    """
    s3_client = get_s3_boto3_client()

    if not is_bucket_existing(s3_client=s3_client, bucket_name=bucket_name):
        LOGGER.warning(f"Bucket {bucket_name} does not exist. Creating it.")
        create_bucket(s3_client=s3_client, bucket_name=bucket_name)

    return s3_client


def upload_file_to_s3(
    file_name: str,
    byte_content: bytes,
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> S3UploadedInformation:
    """Upload a file to an S3 bucket."""
    sanitized_key = sanitize_filename(file_name, remove_extension_dot=False)
    try:
        s3_client = get_s3_client_and_ensure_bucket(bucket_name=bucket_name)
        upload_file_to_bucket(
            s3_client=s3_client, bucket_name=bucket_name, key=sanitized_key, byte_content=byte_content
        )
        LOGGER.info(f"Successfully uploaded file to S3 with {sanitized_key} key.")
        return S3UploadedInformation(s3_path_file=sanitized_key)
    except Exception as e:
        LOGGER.error(f"Error uploading file to S3: {str(e)}")
        raise ValueError(f"Failed to upload file to S3: {str(e)}")


def upload_organization_file_to_s3(
    organization_id: UUID,
    filename: str,
    byte_content: bytes,
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> S3UploadedInformation:
    key = generate_upload_key(organization_id, filename)
    return upload_file_to_s3(file_name=key, byte_content=byte_content, bucket_name=bucket_name)


def delete_file_from_s3(
    key: str,
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> None:
    try:
        s3_client = get_s3_client_and_ensure_bucket(bucket_name=bucket_name)
        delete_file_from_bucket(s3_client=s3_client, bucket_name=bucket_name, key=key)
        LOGGER.info(f"Successfully deleted file from S3 with {key} key.")
    except Exception as e:
        LOGGER.error(f"Error deleting file from S3: {str(e)}")
        raise ValueError(f"Failed to delete file from S3: {str(e)}")


def generate_presigned_upload_url(
    s3_client: boto3.client,
    key: str,
    content_type: str,
    bucket_name: str = settings.S3_BUCKET_NAME,
    expiration: int = 1000,
) -> str:
    """
    Generates a pre-signed URL to upload a file directly from the frontend.
    """
    try:
        url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": bucket_name,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expiration,
        )

        LOGGER.info(f"Generated presigned URL for {key}")
        return url

    except Exception as e:
        LOGGER.error(f"Error generating presigned URL: {str(e)}")
        raise ValueError(f"Couldn't get a presigned URL: {str(e)}") from e


def generate_presigned_download_url(
    s3_client: boto3.client,
    key: str,
    bucket_name: str = settings.S3_BUCKET_NAME,
    expiration: int = 3600,
) -> str:
    try:
        url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": bucket_name,
                "Key": key,
            },
            ExpiresIn=expiration,
        )

        LOGGER.info(f"Generated presigned download URL for {key}")
        return url

    except Exception as e:
        LOGGER.error(f"Error generating presigned download URL: {str(e)}")
        raise ValueError(f"Couldn't get a presigned download URL: {str(e)}") from e


def generate_s3_upload_presigned_urls_service(
    organization_id: UUID,
    upload_file_requests: list[UploadFileRequest],
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> list[S3UploadURL]:
    s3_client = get_s3_client_and_ensure_bucket(bucket_name=bucket_name)
    upload_urls = []
    for upload_file_request in upload_file_requests:
        key = generate_upload_key(organization_id, upload_file_request.filename)
        presigned_url = generate_presigned_upload_url(
            s3_client=s3_client,
            key=key,
            content_type=upload_file_request.content_type,
            bucket_name=bucket_name,
        )
        upload_urls.append(
            S3UploadURL(
                filename=upload_file_request.filename,
                presigned_url=presigned_url,
                key=key,
                content_type=upload_file_request.content_type,
            )
        )
    return upload_urls


def init_multipart_upload(
    organization_id: UUID,
    filename: str,
    content_type: str,
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> MultipartInitResponse:
    s3_client = get_s3_client_and_ensure_bucket(bucket_name=bucket_name)
    key = generate_upload_key(organization_id, filename)
    try:
        response = s3_client.create_multipart_upload(Bucket=bucket_name, Key=key, ContentType=content_type)
        upload_id = response["UploadId"]
        LOGGER.info(f"Initiated multipart upload for {key}, upload_id={upload_id}")
        return MultipartInitResponse(upload_id=upload_id, key=key)
    except Exception as e:
        LOGGER.error(f"Failed to initiate multipart upload for {key}: {e}")
        raise ValueError(f"Failed to initiate multipart upload: {e}") from e


def generate_presigned_part_urls(
    key: str,
    upload_id: str,
    part_count: int,
    bucket_name: str = settings.S3_BUCKET_NAME,
    expiration: int = 3600,
) -> list[PresignedPartURL]:
    s3_client = get_s3_client_and_ensure_bucket(bucket_name=bucket_name)
    urls: list[PresignedPartURL] = []
    try:
        for part_number in range(1, part_count + 1):
            url = s3_client.generate_presigned_url(
                ClientMethod="upload_part",
                Params={
                    "Bucket": bucket_name,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                },
                ExpiresIn=expiration,
            )
            urls.append(PresignedPartURL(part_number=part_number, presigned_url=url))
        LOGGER.info(f"Generated {part_count} presigned part URLs for {key}")
        return urls
    except Exception as e:
        LOGGER.error(f"Failed to generate presigned part URLs for {key}: {e}")
        raise ValueError(f"Failed to generate presigned part URLs: {e}") from e


def complete_multipart_upload(
    key: str,
    upload_id: str,
    parts: list[CompletedPart],
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> None:
    s3_client = get_s3_client_and_ensure_bucket(bucket_name=bucket_name)
    try:
        s3_client.complete_multipart_upload(
            Bucket=bucket_name,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [{"PartNumber": p.part_number, "ETag": p.etag} for p in parts],
            },
        )
        LOGGER.info(f"Completed multipart upload for {key}")
    except Exception as e:
        LOGGER.error(f"Failed to complete multipart upload for {key}: {e}")
        raise ValueError(f"Failed to complete multipart upload: {e}") from e


def abort_multipart_upload(
    key: str,
    upload_id: str,
    bucket_name: str = settings.S3_BUCKET_NAME,
) -> None:
    s3_client = get_s3_client_and_ensure_bucket(bucket_name=bucket_name)
    try:
        s3_client.abort_multipart_upload(Bucket=bucket_name, Key=key, UploadId=upload_id)
        LOGGER.info(f"Aborted multipart upload for {key}")
    except Exception as e:
        LOGGER.error(f"Failed to abort multipart upload for {key}: {e}")
        raise ValueError(f"Failed to abort multipart upload: {e}") from e
