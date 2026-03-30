import json
import logging
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict

import redis
import sentry_sdk
from dotenv import load_dotenv

from settings import settings

logger = logging.getLogger(__name__)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

dotenv_path = Path(__file__).parent.parent / ".env"
logger.info("loading_env_vars path=%s", dotenv_path)
load_dotenv(dotenv_path=dotenv_path)

if settings.SENTRY_DSN_REDIS:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN_REDIS,
        environment=settings.SENTRY_ENVIRONMENT,
        send_default_pii=False,
        enable_logs=True,
        traces_sample_rate=0.1,
    )

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
CONSUMER_GROUP = os.getenv("REDIS_CONSUMER_GROUP", "ada_workers")

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)

# How long (ms) a PEL entry must be idle before it is reclaimed on startup.
_PENDING_IDLE_THRESHOLD_MS = 60_000

# Max delivery attempts before a message is dead-lettered.
_MAX_DELIVERY_ATTEMPTS = int(os.getenv("MAX_DELIVERY_ATTEMPTS", "3"))

# Dead-letter stream suffix — appended to the main stream name.
_DEADLETTER_SUFFIX = ":deadletter"


def _xgroup_create_if_not_exists(stream_name: str, group_name: str) -> None:
    """Create a consumer group on the stream, creating the stream if absent."""
    try:
        redis_client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        logger.info("consumer_group_created stream=%s group=%s", stream_name, group_name)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug("consumer_group_already_exists stream=%s group=%s", stream_name, group_name)
        else:
            logger.error(
                "consumer_group_create_failed stream=%s group=%s error=%s",
                stream_name,
                group_name,
                str(e),
            )
            raise


class BaseWorker:
    """Base class for Redis Streams workers with crash-safe delivery."""

    def __init__(self, stream_name: str, max_concurrent: int, worker_type: str):
        self.stream_name = stream_name
        self.max_concurrent = max_concurrent
        self.current_threads = 0
        self.lock = threading.Lock()
        self.worker_type = worker_type

        if settings.SENTRY_DSN_REDIS:
            sentry_sdk.set_tag("worker_type", worker_type)
            sentry_sdk.set_tag("redis_stream", stream_name)
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

    def _dead_letter(self, message_id: str, fields: Dict[str, str], delivery_count: int, reason: str) -> None:
        """Move a poison message to the dead-letter stream, ACK it, and log."""
        dl_stream = self.stream_name + _DEADLETTER_SUFFIX
        try:
            # Preserve original payload + add diagnostics
            dl_entry = {
                **fields,
                "_original_stream": self.stream_name,
                "_original_message_id": message_id,
                "_delivery_count": str(delivery_count),
                "_reason": reason,
                "_dead_lettered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            redis_client.xadd(dl_stream, dl_entry)
            redis_client.xack(self.stream_name, CONSUMER_GROUP, message_id)
            logger.error(
                "message_dead_lettered stream=%s message_id=%s delivery_count=%s reason=%s dead_letter_stream=%s",
                self.stream_name,
                message_id,
                delivery_count,
                reason,
                dl_stream,
            )
        except Exception as e:
            # Last resort: ACK anyway to stop the crash loop
            logger.error("dead_letter_failed_forcing_ack message_id=%s error=%s", message_id, str(e))
            try:
                redis_client.xack(self.stream_name, CONSUMER_GROUP, message_id)
            except Exception:
                pass

    def _reclaim_pending(self, consumer_name: str) -> None:
        """
        Reclaim PEL entries that have been idle long enough to indicate their
        previous consumer crashed without acknowledging them.

        Dead-letters messages that exceeded _MAX_DELIVERY_ATTEMPTS, then
        reclaims remaining messages **one at a time**, only while the worker
        has capacity.  This prevents xautoclaim from inflating the delivery
        count of messages that cannot be dispatched yet.
        """
        try:
            pending_details = redis_client.xpending_range(self.stream_name, CONSUMER_GROUP, "-", "+", count=100)
            logger.info("pending_entries stream=%s count=%s", self.stream_name, len(pending_details))
            poison_ids: set = set()
            for entry in pending_details:
                mid = entry["message_id"]
                deliveries = entry["times_delivered"]
                idle_ms = entry["time_since_delivered"]
                if deliveries >= _MAX_DELIVERY_ATTEMPTS and idle_ms >= _PENDING_IDLE_THRESHOLD_MS:
                    msgs = redis_client.xrange(self.stream_name, min=mid, max=mid, count=1)
                    fields = msgs[0][1] if msgs else {}
                    reason = f"exceeded max delivery attempts ({deliveries}/{_MAX_DELIVERY_ATTEMPTS})"
                    self._dead_letter(mid, fields, deliveries, reason)
                    self._on_dead_letter(mid, fields, reason)
                    poison_ids.add(mid)

            reclaimed = 0
            start_id = "0-0"
            while self._can_process():
                start_id, messages, _deleted = redis_client.xautoclaim(
                    self.stream_name,
                    CONSUMER_GROUP,
                    consumer_name,
                    _PENDING_IDLE_THRESHOLD_MS,
                    start_id=start_id,
                    count=1,
                )
                if not messages:
                    if start_id == "0-0":
                        break
                    continue
                mid, fields = messages[0]
                if mid in poison_ids:
                    continue
                self._dispatch(mid, fields, consumer_name)
                reclaimed += 1
            if reclaimed:
                logger.info(
                    "reclaimed_pending_messages stream=%s count=%s",
                    self.stream_name,
                    reclaimed,
                )
        except redis.exceptions.ResponseError as e:
            if "ERR" in str(e) or "NOGROUP" in str(e):
                logger.debug("xautoclaim_skipped stream=%s error=%s", self.stream_name, str(e))
            else:
                logger.error("xautoclaim_failed stream=%s error=%s", self.stream_name, str(e))

    def _dispatch(self, message_id: str, fields: Dict[str, str], consumer_name: str) -> None:
        """Parse a raw stream entry and dispatch it to a worker thread."""
        raw = fields.get("data", "")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("invalid_json error=%s stream=%s message_id=%s", str(e), self.stream_name, message_id)
            redis_client.xack(self.stream_name, CONSUMER_GROUP, message_id)
            return

        if not self._validate_payload(payload, self.get_required_fields()):
            logger.error("invalid_payload_format stream=%s message_id=%s", self.stream_name, message_id)
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
                logger.error("xack_failed stream=%s message_id=%s error=%s", self.stream_name, message_id, str(e))
            self._decrement_thread_count()

    _RECLAIM_INTERVAL_S = 30

    def run(self) -> None:
        """Main worker loop — crash-safe via Redis Streams consumer groups."""
        consumer_name = self._consumer_name()
        logger.info(
            "worker_starting stream=%s consumer=%s group=%s",
            self.stream_name,
            consumer_name,
            CONSUMER_GROUP,
        )

        self._reclaim_pending(consumer_name)
        last_reclaim = time.monotonic()

        while True:
            try:
                if not self._can_process():
                    time.sleep(0.5)
                    continue

                now = time.monotonic()
                if now - last_reclaim >= self._RECLAIM_INTERVAL_S:
                    self._reclaim_pending(consumer_name)
                    last_reclaim = now
                    if not self._can_process():
                        continue

                results = redis_client.xreadgroup(
                    CONSUMER_GROUP,
                    consumer_name,
                    {self.stream_name: ">"},
                    count=1,
                    block=5000,
                )

                if not results:
                    continue

                _stream, messages = results[0]
                message_id, fields = messages[0]
                self._dispatch(message_id, fields, consumer_name)

            except redis.ConnectionError:
                logger.warning("redis_connection_error stream=%s retry_in_seconds=%s", self.stream_name, 5)
                time.sleep(5)
            except Exception as e:
                logger.error("unexpected_error error=%s stream=%s", str(e), self.stream_name)
                time.sleep(1)

    def get_required_fields(self) -> list[str]:
        """Return required payload field names. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement get_required_fields")

    def _on_dead_letter(self, message_id: str, fields: Dict[str, str], reason: str = "") -> None:
        """Called when a message is dead-lettered.  Override in subclasses to
        mark the task as failed in the API, send alerts, etc."""
        pass

    def _log_queued_task(self, payload: Dict[str, Any]) -> None:
        """
        Called when a message arrives but the worker is already at max concurrency.
        The message remains unacknowledged in the PEL and will be reclaimed on
        the next worker restart (or by another idle consumer).
        """
        logger.info("task_deferred_pending_capacity stream=%s", self.stream_name)
