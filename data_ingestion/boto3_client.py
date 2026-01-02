import logging
import re
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from settings import settings

LOGGER = logging.getLogger(__name__)

DEFAULT_CONFIG_SIGNATURE_VERSION = "s3v4"
DEFAULT_CONFIG_S3 = {"addressing_style": "path"}


def get_s3_boto3_client(
    endpoint_url: str = settings.S3_ENDPOINT_URL,
    aws_access_key_id: str = settings.S3_ACCESS_KEY_ID,
    aws_secret_access_key: str = settings.S3_SECRET_ACCESS_KEY,
    region_name: str = settings.S3_REGION_NAME,
    config_signature_version: Optional[str] = None,
    config_s3: Optional[dict] = None,
) -> boto3.client:
    if config_signature_version is None:
        config_signature_version = DEFAULT_CONFIG_SIGNATURE_VERSION
    if config_s3 is None:
        config_s3 = DEFAULT_CONFIG_S3
    try:
        if endpoint_url is None or len(endpoint_url) == 0:
            # We are using AWS S3 bucket, we can skip the endpoint_url
            LOGGER.info("Using default AWS S3 endpoint.")
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name,
                config=Config(signature_version=config_signature_version, s3=config_s3),
            )
        else:
            # We are using custom S3 endpoint, we need to provide the endpoint_url
            LOGGER.info(f"Using custom S3 endpoint: {endpoint_url}")
            s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name,
                config=Config(signature_version=config_signature_version, s3=config_s3),
            )
        LOGGER.info("Successfully created S3 client.")
        return s3_client
    except Exception as e:
        LOGGER.error(f"Failed to create S3 client: {str(e)}")
        raise ValueError(f"Failed to create S3 client: {str(e)}")


def is_bucket_existing(s3_client, bucket_name: str) -> bool:
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        LOGGER.info(f"Bucket {bucket_name} already exists.")
        return True
    except ClientError as e:
        error_code = int(e.response["Error"]["Code"])
        if error_code == 404:
            return False
        else:
            LOGGER.error(f"Error with client error checking bucket existence: {e}")
            return False
    except Exception as e:
        LOGGER.error(f"Unexpected error checking bucket: {e}")
        return False


def create_bucket(s3_client, bucket_name: str) -> bool:
    if not is_valid_bucket_name(bucket_name):
        LOGGER.error(f"Invalid bucket name: '{bucket_name}'")
        return False
    try:
        s3_client.create_bucket(Bucket=bucket_name)
        LOGGER.info(f"Bucket '{bucket_name}' created successfully.")
    except Exception as e:
        LOGGER.error(f"Failed to create bucket: {e}")


def upload_file_to_bucket(s3_client, bucket_name: str, key: str, byte_content: bytes) -> None:
    """"""
    try:
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=byte_content)
        LOGGER.info(f"Successfully Uploaded to s3 '{key}' on the  bucket '{bucket_name}'.")
    except Exception as e:
        LOGGER.error(f"Unexpected error while uploading '{key}' to bucket '{bucket_name}': {e}")
        raise ValueError(f"Failed to upload file '{key}' to bucket '{bucket_name}': {e}")


def delete_file_from_bucket(s3_client, bucket_name: str, key: str) -> None:
    """"""
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=key)
        LOGGER.info(f"Successfully deleted '{key}' from bucket '{bucket_name}'.")
    except Exception as e:
        LOGGER.error(f"Unexpected error deleting '{key}' from bucket '{bucket_name}': {e}")
        raise ValueError(f"Failed to upload file '{key}' to bucket '{bucket_name}': {e}")


def is_valid_bucket_name(name: str) -> bool:
    return bool(re.fullmatch(r"^[a-z0-9]([a-z0-9-]{1,61}[a-z0-9])?$", name))


def file_exists_in_bucket(s3_client, bucket_name: str, key: str) -> bool:
    try:
        s3_client.head_object(Bucket=bucket_name, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            LOGGER.debug(f"File does not exist in bucket {bucket_name}: {key}")
            return False
        LOGGER.error(f"Error checking if file {key} exists in bucket {bucket_name}: {e}")


def get_content_from_file(s3_client, bucket_name: str, key: str) -> Optional[bytes]:
    """"""
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        return response["Body"].read()
    except ClientError as e:
        LOGGER.error(f"Error retrieving file {key} from bucket {bucket_name}: {e}")
        raise ValueError(f"Failed to retrieve file {key} from bucket {bucket_name}: {e}")
