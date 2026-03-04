import json
import logging
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict

import redis
import structlog
from dotenv import load_dotenv

# TODO: use same logging as the rest of the code
structlog.configure(
    processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

dotenv_path = Path(__file__).parent.parent / ".env"
logger.info(f"Loading environment variables from {dotenv_path}")
load_dotenv(dotenv_path=dotenv_path)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
CONSUMER_GROUP = os.getenv("REDIS_CONSUMER_GROUP", "ada_workers")

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)

# How long (ms) a PEL entry must be idle before it is reclaimed on startup.
_PENDING_IDLE_THRESHOLD_MS = 60_000


def _xgroup_create_if_not_exists(stream_name: str, group_name: str) -> None:
    """Create a consumer group on the stream, creating the stream if absent."""
    try:
        redis_client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        logger.info("consumer_group_created", stream=stream_name, group=group_name)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug("consumer_group_already_exists", stream=stream_name, group=group_name)
        else:
            logger.error("consumer_group_create_failed", stream=stream_name, group=group_name, error=str(e))
            raise


class BaseWorker:
    """Base class for Redis Streams workers with crash-safe delivery."""

    def __init__(self, stream_name: str, max_concurrent: int):
        self.stream_name = stream_name
        self.max_concurrent = max_concurrent
        self.current_threads = 0
        self.lock = threading.Lock()
        # Ensure the stream and consumer group exist before the loop starts.
        _xgroup_create_if_not_exists(self.stream_name, CONSUMER_GROUP)

    def _consumer_name(self) -> str:
        return f"{socket.gethostname()}-{os.getpid()}"

    def _can_process(self) -> bool:
        with self.lock:
            return self.current_threads < self.max_concurrent

    def _reserve_slot(self) -> bool:
        with self.lock:
            if self.current_threads < self.max_concurrent:
                self.current_threads += 1
                return True
            return False

    def _decrement_thread_count(self) -> None:
        with self.lock:
            self.current_threads -= 1

    def process_task(self, payload: Dict[str, Any]) -> None:
        """Process a single task. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement process_task")

    def _validate_payload(self, payload: Dict[str, Any], required_fields: list[str]) -> bool:
        if not isinstance(payload, dict):
            return False
        return all(field in payload for field in required_fields)

    def _reclaim_pending(self, consumer_name: str) -> None:
        """
        On startup, reclaim PEL entries that have been idle long enough to
        indicate their previous consumer crashed without acknowledging them.
        Reclaimed messages are processed immediately like fresh messages.
        """
        try:
            _next, messages, _deleted = redis_client.xautoclaim(
                self.stream_name,
                CONSUMER_GROUP,
                consumer_name,
                _PENDING_IDLE_THRESHOLD_MS,
                start_id="0-0",
                count=100,
            )
            if messages:
                logger.info(
                    "reclaimed_pending_messages",
                    stream=self.stream_name,
                    count=len(messages),
                )
                for message_id, fields in messages:
                    self._dispatch(message_id, fields, consumer_name)
        except redis.exceptions.ResponseError as e:
            # Stream or group may not exist yet on a completely fresh deployment.
            if "ERR" in str(e) or "NOGROUP" in str(e):
                logger.debug("xautoclaim_skipped", stream=self.stream_name, error=str(e))
            else:
                logger.error("xautoclaim_failed", stream=self.stream_name, error=str(e))

    def _dispatch(self, message_id: str, fields: Dict[str, str], consumer_name: str) -> None:
        """Parse a raw stream entry and dispatch it to a worker thread."""
        raw = fields.get("data", "")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("invalid_json", error=str(e), stream=self.stream_name, message_id=message_id)
            redis_client.xack(self.stream_name, CONSUMER_GROUP, message_id)
            return

        if not self._validate_payload(payload, self.get_required_fields()):
            logger.error("invalid_payload_format", stream=self.stream_name, message_id=message_id)
            redis_client.xack(self.stream_name, CONSUMER_GROUP, message_id)
            return

        if self._reserve_slot():
            thread = threading.Thread(
                target=self._process_and_ack,
                args=(payload, message_id),
                daemon=True,
            )
            thread.start()
        else:
            # Should not reach here — we only read when a slot is free — but
            # guard defensively: leave the message unacknowledged so it is
            # visible to XAUTOCLAIM on the next startup.
            self._log_queued_task(payload)

    def _process_and_ack(self, payload: Dict[str, Any], message_id: str) -> None:
        """Run process_task and acknowledge the message regardless of outcome."""
        try:
            self.process_task(payload)
        finally:
            try:
                redis_client.xack(self.stream_name, CONSUMER_GROUP, message_id)
            except Exception as e:
                logger.error("xack_failed", stream=self.stream_name, message_id=message_id, error=str(e))
            self._decrement_thread_count()

    def run(self) -> None:
        """Main worker loop — crash-safe via Redis Streams consumer groups."""
        consumer_name = self._consumer_name()
        logger.info("worker_starting", stream=self.stream_name, consumer=consumer_name, group=CONSUMER_GROUP)

        # Recover any messages that were mid-flight when a previous instance crashed.
        self._reclaim_pending(consumer_name)

        while True:
            try:
                # Back-pressure: don't pull new work while at capacity.
                if not self._can_process():
                    time.sleep(0.5)
                    continue

                results = redis_client.xreadgroup(
                    CONSUMER_GROUP,
                    consumer_name,
                    {self.stream_name: ">"},
                    count=1,
                    block=5000,
                )

                if not results:
                    # Timeout — loop to check capacity and try again.
                    continue

                _stream, messages = results[0]
                message_id, fields = messages[0]
                self._dispatch(message_id, fields, consumer_name)

            except redis.ConnectionError:
                logger.warning(
                    "redis_connection_error",
                    stream=self.stream_name,
                    retry_in_seconds=5,
                )
                time.sleep(5)
            except Exception as e:
                logger.error("unexpected_error", error=str(e), stream=self.stream_name)
                time.sleep(1)

    def get_required_fields(self) -> list[str]:
        """Return required payload field names. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement get_required_fields")

    def _log_queued_task(self, payload: Dict[str, Any]) -> None:
        """
        Called when a message arrives but the worker is already at max concurrency.
        The message remains unacknowledged in the PEL and will be reclaimed on
        the next worker restart (or by another idle consumer).
        """
        logger.info("task_deferred_pending_capacity", stream=self.stream_name)
