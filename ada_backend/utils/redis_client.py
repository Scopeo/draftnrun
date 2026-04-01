import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import redis
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

from ada_backend.schemas.ingestion_task_schema import SourceAttributes
from settings import settings

LOGGER = logging.getLogger(__name__)

# Module-level Redis client cache to avoid creating a new connection on every call.
_redis_client: Optional[redis.Redis] = None
_last_health_check: float = 0.0

# Seconds between proactive ping checks on the cached client.
_HEALTH_CHECK_INTERVAL = 30.0
# Number of automatic retries on transient connection failures.
_MAX_RETRIES = 3

_RECONNECT_ERRORS = (
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
    redis.exceptions.BusyLoadingError,
)


def reset_redis_client() -> None:
    """
    Discard the cached Redis client so the next get_redis_client() call
    creates a fresh connection. Call this after catching a connection error
    that exhausted all built-in retries.
    """
    global _redis_client
    _redis_client = None
    LOGGER.info("Redis client reset — will reconnect on next call.")


def get_redis_client() -> Optional[redis.Redis]:
    """
    Return a healthy Redis client, reconnecting automatically when the cached
    connection has gone stale.

    Reconnection is triggered in two ways:
    - Proactive: a ping is issued every _HEALTH_CHECK_INTERVAL seconds.
    - Reactive: callers that catch _RECONNECT_ERRORS should call
      reset_redis_client() so the next invocation rebuilds the connection.

    The client is created with built-in exponential-backoff retry for
    transient errors, and redis-py's health_check_interval so the pool
    tests idle connections before handing them out.
    """
    global _redis_client, _last_health_check

    if not settings.REDIS_HOST:
        LOGGER.warning("Redis host not configured. Skipping Redis client initialization.")
        return None

    now = time.monotonic()

    if _redis_client is not None:
        # Periodically verify the cached connection is still alive.
        if now - _last_health_check >= _HEALTH_CHECK_INTERVAL:
            try:
                _redis_client.ping()
                _last_health_check = now
            except _RECONNECT_ERRORS as e:
                LOGGER.warning("Redis health-check ping failed, reconnecting: %s", e)
                _redis_client = None

        if _redis_client is not None:
            return _redis_client

    LOGGER.debug("Connecting to Redis at %s:%s", settings.REDIS_HOST, settings.REDIS_PORT)

    try:
        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
            retry=Retry(ExponentialBackoff(cap=10, base=1), _MAX_RETRIES),
            retry_on_error=list(_RECONNECT_ERRORS),
            health_check_interval=int(_HEALTH_CHECK_INTERVAL),
        )
        client.ping()
        _redis_client = client
        _last_health_check = time.monotonic()
        LOGGER.info("Connected to Redis at %s:%s", settings.REDIS_HOST, settings.REDIS_PORT)
        return _redis_client
    except Exception as e:
        LOGGER.error("Failed to connect to Redis: %s", e)
        _redis_client = None
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
    except _RECONNECT_ERRORS as e:
        LOGGER.error("Redis connection error during xreadgroup on stream '%s': %s", stream_name, e)
        reset_redis_client()
        return None
    except redis.exceptions.ResponseError as e:
        LOGGER.error("xreadgroup error on stream '%s': %s", stream_name, e)
        return None


def xack(stream_name: str, group_name: str, message_id: str) -> None:
    """Acknowledge that a message has been fully processed."""
    client = get_redis_client()
    if not client:
        return

    try:
        client.xack(stream_name, group_name, message_id)
    except _RECONNECT_ERRORS as e:
        LOGGER.error("Redis connection error during XACK of %s on stream '%s': %s", message_id, stream_name, e)
        reset_redis_client()
    except Exception as e:
        LOGGER.error("Failed to XACK message %s on stream '%s': %s", message_id, stream_name, e)


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

    except _RECONNECT_ERRORS as e:
        LOGGER.error("Redis connection error pushing ingestion task %s: %s", ingestion_id, e)
        reset_redis_client()
        return False
    except Exception as e:
        LOGGER.error("Failed to push ingestion task %s to Redis stream: %s", ingestion_id, e)
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
    except _RECONNECT_ERRORS as e:
        LOGGER.error("Redis connection error during webhook deduplication. Allowing event to proceed: %s", e)
        reset_redis_client()
        return True
    except Exception as e:
        LOGGER.error("Failed to perform webhook deduplication. Allowing event to proceed: %s", e)
        return True


def push_webhook_event(
    webhook_id: UUID,
    provider: str,
    payload: Dict[str, Any],
    event_id: str,
    organization_id: Optional[UUID] = None,
    run_id: Optional[str] = None,
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
        if run_id:
            queue_payload["run_id"] = run_id

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

    except _RECONNECT_ERRORS as e:
        LOGGER.error("Redis connection error pushing webhook event %s: %s", event_id, e)
        reset_redis_client()
        return False
    except Exception as e:
        LOGGER.error("Failed to push webhook event %s to Redis stream: %s", event_id, e)
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
    except _RECONNECT_ERRORS as e:
        LOGGER.error("Redis connection error pushing run %s to queue: %s", run_id, e)
        reset_redis_client()
        return False
    except Exception as e:
        LOGGER.error("Failed to push run %s to Redis queue: %s", run_id, e)
        return False


def push_qa_task(
    session_id: UUID,
    project_id: UUID,
    dataset_id: UUID,
    run_request_data: Dict[str, Any],
) -> bool:
    client = get_redis_client()
    if not client:
        LOGGER.error("Redis client unavailable. Cannot push QA task for session %s", session_id)
        return False

    try:
        payload = {
            "session_id": str(session_id),
            "project_id": str(project_id),
            "dataset_id": str(dataset_id),
            "run_request": run_request_data,
        }
        json_payload = json.dumps(payload)
        result = client.rpush(settings.REDIS_QA_QUEUE_NAME, json_payload)
        if result:
            LOGGER.info(
                "Pushed QA task (session %s) to Redis queue %s (queue length: %s)",
                session_id,
                settings.REDIS_QA_QUEUE_NAME,
                result,
            )
            return True
        LOGGER.warning("Redis returned %s when pushing to queue %s", result, settings.REDIS_QA_QUEUE_NAME)
        return False
    except _RECONNECT_ERRORS as e:
        LOGGER.error("Redis connection error pushing QA task %s to queue: %s", session_id, e)
        reset_redis_client()
        return False
    except Exception as e:
        LOGGER.error("Failed to push QA task %s to Redis queue: %s", session_id, e)
        return False


def publish_event(channel_prefix: str, resource_id: UUID, event: Dict[str, Any]) -> bool:
    """
    Publish an event to Redis Pub/Sub channel {channel_prefix}:{resource_id}.
    Used by workers to stream events to WebSocket subscribers.
    """
    client = get_redis_client()
    if not client:
        LOGGER.debug("Redis client unavailable. Cannot publish event to %s:%s", channel_prefix, resource_id)
        return False
    try:
        channel = f"{channel_prefix}:{resource_id}"
        message = json.dumps(event)
        count = client.publish(channel, message)
        LOGGER.debug("Published event to %s (%s subscribers)", channel, count)
        return True
    except _RECONNECT_ERRORS as e:
        LOGGER.error("Redis connection error publishing to %s:%s: %s", channel_prefix, resource_id, e)
        reset_redis_client()
        return False
    except Exception as e:
        LOGGER.error("Failed to publish event to %s:%s: %s", channel_prefix, resource_id, e)
        return False


def publish_run_event(run_id: UUID, event: Dict[str, Any]) -> bool:
    return publish_event("run", run_id, event)


def publish_qa_event(session_id: UUID, event: Dict[str, Any]) -> bool:
    return publish_event("qa", session_id, event)
