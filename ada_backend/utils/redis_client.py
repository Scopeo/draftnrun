import json
import logging
from typing import Optional

import redis

from ada_backend.schemas.ingestion_task_schema import SourceAttributes
from settings import settings

LOGGER = logging.getLogger(__name__)


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get a Redis client instance configured with settings from environment variables.

    Returns:
        Optional[redis.Redis]: Redis client instance or None if configuration is missing
    """
    if not settings.REDIS_HOST:
        LOGGER.warning("Redis host not configured. Skipping Redis client initialization.")
        return None

    LOGGER.debug(f"Connecting to Redis server at {settings.REDIS_HOST}:{settings.REDIS_PORT}")

    try:
        LOGGER.debug("Attempting Redis connection with password")
        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
        )
        # Test connection
        client.ping()
        LOGGER.debug("Successfully connected to Redis server")
        return client
    except Exception as e:
        LOGGER.error(f"Failed to connect to Redis: {str(e)}")
        return None


def push_ingestion_task(
    ingestion_id: str,
    source_name: str,
    source_type: str,
    organization_id: str,
    task_id: str,
    source_attributes: SourceAttributes,
) -> bool:
    """
    Push an ingestion task to the Redis queue.

    Args:
        ingestion_id: ID for the ingestion process
        source_name: Name of the source to ingest
        source_type: Type of the source (e.g., 'drive', 'slack')
        organization_id: ID of the organization
        task_id: ID of the task
        access_token: Authentication token for the source
        folder_id: ID of the folder to ingest (can be empty)

    Returns:
        bool: True if successful, False otherwise
    """
    LOGGER.info(f"Preparing to push ingestion task to Redis: {ingestion_id} for {source_name} ({source_type})")

    client = get_redis_client()
    if not client:
        LOGGER.error(f"Redis client unavailable. Cannot push ingestion task {ingestion_id}")
        return False

    try:
        # Prepare payload with all essential fields
        payload = {
            "ingestion_id": ingestion_id,
            "source_name": source_name,
            "source_type": source_type,
            "organization_id": organization_id,
            "task_id": task_id,
            "source_attributes": source_attributes.model_dump(),
        }

        # TODO: add server logging
        # Create a safe version of the payload for logging (redact sensitive data)
        safe_payload = payload.copy()
        safe_payload["source_attributes"] = safe_payload["source_attributes"].copy()
        if "access_token" in safe_payload["source_attributes"]:
            safe_payload["source_attributes"]["access_token"] = "****REDACTED****"

        LOGGER.debug(f"Prepared payload for Redis: {safe_payload}")

        json_payload = json.dumps(payload)
        result = client.lpush(settings.REDIS_QUEUE_NAME, json_payload)

        if result:
            LOGGER.info(
                f"Successfully pushed task {ingestion_id} to Redis queue "
                f"{settings.REDIS_QUEUE_NAME} (queue length: {result})"
            )
            return True
        else:
            LOGGER.warning(f"Redis returned {result} when pushing to queue {settings.REDIS_QUEUE_NAME}")
            return False

    except Exception as e:
        LOGGER.error(f"Failed to push task {ingestion_id} to Redis queue: {str(e)}")
        return False
