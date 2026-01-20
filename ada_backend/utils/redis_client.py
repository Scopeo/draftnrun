import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

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
    source_id: Optional[str] = None,
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
            "source_id": source_id,
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


def check_and_set_webhook_event(provider: str, event_id: str, ttl: int) -> bool:
    """
    Atomically check and set a webhook event ID for deduplication.

    Returns:
        bool: True if the event is new and was set, False if it was a duplicate.
    """
    client = get_redis_client()
    if not client:
        LOGGER.warning("Redis client unavailable. Cannot perform webhook deduplication. Allowing event to proceed.")
        return True

    try:
        key = f"webhook:dedup:{provider}:{event_id}"
        is_new = client.set(key, "1", ex=ttl, nx=True)
        if not is_new:
            LOGGER.debug(f"Duplicate webhook event detected: provider={provider}, event_id={event_id}")
        return bool(is_new)
    except Exception as e:
        LOGGER.error(f"Failed to perform webhook deduplication. Allowing event to proceed: {str(e)}")
        return True


def push_webhook_event(
    webhook_id: UUID,
    provider: str,
    payload: Dict[str, Any],
    event_id: str,
    organization_id: UUID,
) -> bool:
    """
    Push a webhook event to the Redis queue for async processing.
    """
    LOGGER.info(
        f"Preparing to push webhook event to Redis: provider={provider}, event_id={event_id}, webhook_id={webhook_id}"
    )

    client = get_redis_client()
    if not client:
        LOGGER.error(f"Redis client unavailable. Cannot push webhook event {event_id} to queue")
        return False

    try:
        queue_payload = {
            "webhook_id": str(webhook_id),
            "provider": provider,
            "event_id": event_id,
            "organization_id": str(organization_id),
            "payload": payload,
        }

        safe_payload = queue_payload.copy()
        if "payload" in safe_payload:
            safe_payload["payload"] = {
                k: "***REDACTED***" if k in ["token", "access_token"] else v
                for k, v in safe_payload["payload"].items()
            }

        LOGGER.debug(f"Prepared webhook payload for Redis: {safe_payload}")

        json_payload = json.dumps(queue_payload)
        result = client.lpush(settings.REDIS_WEBHOOK_QUEUE_NAME, json_payload)

        if result:
            LOGGER.info(
                f"Successfully pushed webhook event {event_id} to Redis queue "
                f"{settings.REDIS_WEBHOOK_QUEUE_NAME} (queue length: {result})"
            )
            return True
        else:
            LOGGER.warning(f"Redis returned {result} when pushing to queue {settings.REDIS_WEBHOOK_QUEUE_NAME}")
            return False

    except Exception as e:
        LOGGER.error(f"Failed to push webhook event {event_id} to Redis queue: {str(e)}")
        return False
