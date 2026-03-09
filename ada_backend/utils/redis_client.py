import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import redis

from ada_backend.schemas.ingestion_task_schema import SourceAttributes
from settings import settings

LOGGER = logging.getLogger(__name__)

# Module-level Redis client cache to avoid creating a new connection on every call.
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get a Redis client instance configured with settings from environment variables.

    Returns:
        Optional[redis.Redis]: Redis client instance or None if configuration is missing
    """
    global _redis_client

    if not settings.REDIS_HOST:
        LOGGER.warning("Redis host not configured. Skipping Redis client initialization.")
        return None

    # Reuse existing client if already initialized
    if _redis_client is not None:
        return _redis_client

    LOGGER.debug(f"Connecting to Redis server at {settings.REDIS_HOST}:{settings.REDIS_PORT}")

    try:
        LOGGER.debug("Attempting Redis connection with password")
        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
        )
        # Test connection once and cache the client
        client.ping()
        LOGGER.debug("Successfully connected to Redis server")
        _redis_client = client
        return _redis_client
    except Exception as e:
        LOGGER.error(f"Failed to connect to Redis: {str(e)}")
        return None


def xgroup_create_if_not_exists(stream_name: str, group_name: str) -> None:
    """
    Create a Redis Streams consumer group if it does not already exist.

    Uses MKSTREAM so the stream itself is created when absent.
    Uses id="0" so the group sees all historical messages (important for
    crash recovery on first boot).
    """
    client = get_redis_client()
    if not client:
        LOGGER.warning(
            f"Redis client unavailable. Cannot create consumer group '{group_name}' on stream '{stream_name}'."
        )
        return

    try:
        client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        LOGGER.info(f"Created consumer group '{group_name}' on stream '{stream_name}'.")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            LOGGER.debug(f"Consumer group '{group_name}' already exists on stream '{stream_name}'.")
        else:
            LOGGER.error(f"Failed to create consumer group '{group_name}' on stream '{stream_name}': {e}")
            raise


def xreadgroup_single(
    stream_name: str,
    group_name: str,
    consumer_name: str,
    block_ms: int = 5000,
) -> Optional[Tuple[str, Dict[str, str]]]:
    """
    Read one new message from a stream as a named consumer group member.

    Blocks for up to *block_ms* milliseconds waiting for a message.

    Returns:
        (message_id, fields_dict) — the raw stream entry, or None on timeout.
    """
    client = get_redis_client()
    if not client:
        return None

    try:
        results = client.xreadgroup(
            group_name,
            consumer_name,
            {stream_name: ">"},
            count=1,
            block=block_ms,
        )
        if not results:
            return None
        # results: [(stream_name, [(message_id, fields_dict)])]
        _stream, messages = results[0]
        message_id, fields = messages[0]
        return message_id, fields
    except redis.exceptions.ResponseError as e:
        LOGGER.error(f"xreadgroup error on stream '{stream_name}': {e}")
        return None


def xack(stream_name: str, group_name: str, message_id: str) -> None:
    """Acknowledge that a message has been fully processed."""
    client = get_redis_client()
    if not client:
        return

    try:
        client.xack(stream_name, group_name, message_id)
    except Exception as e:
        LOGGER.error(f"Failed to XACK message {message_id} on stream '{stream_name}': {e}")


def xautoclaim_pending(
    stream_name: str,
    group_name: str,
    consumer_name: str,
    min_idle_ms: int = 60_000,
) -> List[Tuple[str, Dict[str, str]]]:
    """
    Reclaim pending messages that have been idle for at least *min_idle_ms* ms.
    Intended to be called once at worker startup for crash recovery.

    Returns:
        List of (message_id, fields_dict) tuples ready for reprocessing.
    """
    client = get_redis_client()
    if not client:
        return []

    try:
        # xautoclaim returns (next_start_id, [(id, fields), ...], [deleted_ids])
        _next, messages, _deleted = client.xautoclaim(
            stream_name,
            group_name,
            consumer_name,
            min_idle_ms,
            start_id="0-0",
            count=100,
        )
        if messages:
            LOGGER.info(f"Reclaimed {len(messages)} stale pending message(s) on stream '{stream_name}'.")
        return [(mid, fields) for mid, fields in messages]
    except redis.exceptions.ResponseError as e:
        # Stream or group may not exist yet on a fresh deployment
        if "ERR" in str(e) or "NOGROUP" in str(e):
            LOGGER.debug(f"xautoclaim skipped for '{stream_name}': {e}")
            return []
        LOGGER.error(f"xautoclaim failed on stream '{stream_name}': {e}")
        return []


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
    Push an ingestion task onto the Redis Stream.

    Returns:
        bool: True if the message was added, False otherwise.
    """
    LOGGER.info(f"Preparing to push ingestion task to Redis stream: {ingestion_id} for {source_name} ({source_type})")

    client = get_redis_client()
    if not client:
        LOGGER.error(f"Redis client unavailable. Cannot push ingestion task {ingestion_id}")
        return False

    try:
        payload = {
            "ingestion_id": ingestion_id,
            "source_name": source_name,
            "source_type": source_type,
            "organization_id": organization_id,
            "task_id": task_id,
            "source_attributes": source_attributes.model_dump(),
            "source_id": source_id,
        }

        safe_payload = payload.copy()
        safe_payload["source_attributes"] = safe_payload["source_attributes"].copy()
        if "access_token" in safe_payload["source_attributes"]:
            safe_payload["source_attributes"]["access_token"] = "****REDACTED****"

        LOGGER.debug(f"Prepared payload for Redis stream: {safe_payload}")

        message_id = client.xadd(settings.REDIS_INGESTION_STREAM, {"data": json.dumps(payload)})

        LOGGER.info(
            f"Successfully pushed task {ingestion_id} to Redis stream "
            f"'{settings.REDIS_INGESTION_STREAM}' (message_id: {message_id})"
        )
        return True

    except Exception as e:
        LOGGER.error(f"Failed to push task {ingestion_id} to Redis stream: {str(e)}")
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
    organization_id: Optional[UUID] = None,
) -> bool:
    """
    Push a webhook event onto the Redis Stream for async processing.
    """
    LOGGER.info(
        f"Preparing to push webhook event to Redis stream: "
        f"provider={provider}, event_id={event_id}, webhook_id={webhook_id}"
    )

    client = get_redis_client()
    if not client:
        LOGGER.error(f"Redis client unavailable. Cannot push webhook event {event_id} to stream")
        return False

    try:
        queue_payload = {
            "webhook_id": str(webhook_id),
            "provider": provider,
            "event_id": event_id,
            "organization_id": str(organization_id) if organization_id else None,
            "payload": payload,
        }

        safe_payload = queue_payload.copy()
        if "payload" in safe_payload:
            safe_payload["payload"] = {
                k: "***REDACTED***" if k in ["token", "access_token"] else v
                for k, v in safe_payload["payload"].items()
            }

        LOGGER.debug(f"Prepared webhook payload for Redis stream: {safe_payload}")

        message_id = client.xadd(settings.REDIS_WEBHOOK_STREAM, {"data": json.dumps(queue_payload)})

        LOGGER.info(
            f"Successfully pushed webhook event {event_id} to Redis stream "
            f"'{settings.REDIS_WEBHOOK_STREAM}' (message_id: {message_id})"
        )
        return True

    except Exception as e:
        LOGGER.error(f"Failed to push webhook event {event_id} to Redis stream: {str(e)}")
        return False


def push_run_task(
    run_id: UUID,
    project_id: UUID,
    env: str,
    input_data: Dict[str, Any],
    trigger: str = "api",
    response_format: Optional[str] = None,
) -> bool:
    """
    Push an async run task to the Redis runs queue.
    Returns True if successful, False otherwise.
    """
    client = get_redis_client()
    if not client:
        LOGGER.error("Redis client unavailable. Cannot push run task %s", run_id)
        return False

    try:
        payload = {
            "run_id": str(run_id),
            "project_id": str(project_id),
            "env": env,
            "input_data": input_data,
            "trigger": trigger,
            "response_format": response_format,
        }
        json_payload = json.dumps(payload)
        result = client.rpush(settings.REDIS_RUNS_QUEUE_NAME, json_payload)
        if result:
            LOGGER.info(
                "Pushed run %s to Redis queue %s (queue length: %s)",
                run_id,
                settings.REDIS_RUNS_QUEUE_NAME,
                result,
            )
            return True
        LOGGER.warning("Redis returned %s when pushing to queue %s", result, settings.REDIS_RUNS_QUEUE_NAME)
        return False
    except Exception as e:
        LOGGER.error("Failed to push run %s to Redis queue: %s", run_id, e)
        return False


def publish_run_event(run_id: UUID, event: Dict[str, Any]) -> bool:
    """
    Publish a run event to Redis Pub/Sub channel run:{run_id}.
    Used by the worker to stream events to WebSocket subscribers.
    Returns True if at least one subscriber received the message, False on error.
    """
    client = get_redis_client()
    if not client:
        LOGGER.debug("Redis client unavailable. Cannot publish run event for %s", run_id)
        return False
    try:
        channel = f"run:{run_id}"
        message = json.dumps(event)
        count = client.publish(channel, message)
        LOGGER.debug("Published event to %s (%s subscribers)", channel, count)
        return True
    except Exception as e:
        LOGGER.error("Failed to publish run event for %s: %s", run_id, e)
        return False
