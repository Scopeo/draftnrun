import asyncio
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from uuid import uuid4

from ada_backend.utils.redis_client import get_redis_client
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

_HEARTBEAT_TTL = 60
_HEARTBEAT_INTERVAL = 20
_ORPHAN_FOLLOW_UP_DELAY = _HEARTBEAT_TTL
_MAX_ORPHAN_FOLLOW_UPS = 2


class BaseQueueWorker(ABC):
    def __init__(self, queue_name: str, worker_label: str, trace_project_name: str):
        self.queue_name = queue_name
        self.worker_label = worker_label
        self._trace_manager: TraceManager | None = None
        self._trace_project_name = trace_project_name
        self._drain_requested = threading.Event()

    @property
    @abstractmethod
    def required_payload_keys(self) -> tuple[str, ...]:
        ...

    @abstractmethod
    def process_payload(self, payload: dict, loop: asyncio.AbstractEventLoop) -> None:
        ...

    @abstractmethod
    def recover_orphaned_item(self, item_payload: dict) -> None:
        """Reset a stuck entity back to PENDING so it can be retried."""
        ...

    @abstractmethod
    def parse_item_id(self, item_payload: dict):
        """Return the item identifier from a parsed queue payload (for logging). Raise on bad data."""
        ...

    def request_drain(self) -> None:
        self._drain_requested.set()

    def _ensure_trace_manager(self) -> None:
        if self._trace_manager is None:
            self._trace_manager = TraceManager(project_name=self._trace_project_name)
        set_trace_manager(self._trace_manager)

    def start_thread(self) -> threading.Thread | None:
        if not get_redis_client():
            return None
        t = threading.Thread(target=self._worker_loop, daemon=True, name=f"{self.worker_label}-worker")
        t.start()
        return t

    @staticmethod
    def _processing_queue_key(queue_name: str, worker_id: str) -> str:
        return f"{queue_name}:processing:{worker_id}"

    @staticmethod
    def _heartbeat_key(queue_name: str, worker_id: str) -> str:
        return f"{queue_name}:worker:{worker_id}:alive"

    @staticmethod
    def _cleanup_worker_keys(client, queue_name: str, worker_id: str) -> None:
        try:
            client.delete(
                BaseQueueWorker._processing_queue_key(queue_name, worker_id),
                BaseQueueWorker._heartbeat_key(queue_name, worker_id),
            )
            LOGGER.debug("Cleaned up Redis keys for worker %s", worker_id)
        except Exception as e:
            LOGGER.warning("Failed to clean up Redis keys for worker %s: %s", worker_id, e)

    @staticmethod
    def _heartbeat_loop(client, heartbeat_key: str, stop_event: threading.Event) -> None:
        while not stop_event.wait(timeout=_HEARTBEAT_INTERVAL):
            try:
                client.set(heartbeat_key, "1", ex=_HEARTBEAT_TTL)
            except Exception as e:
                LOGGER.warning("Failed to refresh worker heartbeat %s: %s", heartbeat_key, e)

    def _recover_orphaned_processing_queues(self, client, own_processing_queue: str) -> None:
        prefix = f"{self.queue_name}:processing:"
        try:
            cursor = 0
            while True:
                cursor, keys = client.scan(cursor, match=f"{prefix}*", count=100)
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    if key_str == own_processing_queue:
                        continue

                    orphan_worker_id = key_str[len(prefix):]

                    if client.exists(self._heartbeat_key(self.queue_name, orphan_worker_id)):
                        continue

                    LOGGER.info(
                        "[%s] Recovering orphaned processing queue for dead worker %s",
                        self.worker_label,
                        orphan_worker_id,
                    )
                    while True:
                        item = client.rpop(key_str)
                        if item is None:
                            break
                        try:
                            item_payload = json.loads(item)
                            self.parse_item_id(item_payload)
                        except Exception:
                            LOGGER.warning(
                                "[%s] Discarding malformed item from orphaned queue of worker %s",
                                self.worker_label,
                                orphan_worker_id,
                            )
                            continue

                        try:
                            self.recover_orphaned_item(item_payload)
                        except Exception as e:
                            LOGGER.exception(
                                "[%s] Error resetting stuck item to PENDING: %s", self.worker_label, e,
                            )

                        try:
                            client.lpush(self.queue_name, item)
                        except Exception as push_exc:
                            LOGGER.exception(
                                "[%s] Failed to re-enqueue recovered item %s (stranded in PENDING): %s",
                                self.worker_label,
                                self.parse_item_id(item_payload),
                                push_exc,
                            )

                    self._cleanup_worker_keys(client, self.queue_name, orphan_worker_id)

                if cursor == 0:
                    break
        except Exception as e:
            LOGGER.exception("[%s] Error recovering orphaned processing queues: %s", self.worker_label, e)

    def _worker_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        client = get_redis_client()
        if not client:
            LOGGER.warning("[%s] Redis client unavailable, worker not starting", self.worker_label)
            return

        worker_id = str(uuid4())
        processing_queue_name = self._processing_queue_key(self.queue_name, worker_id)
        hb_key = self._heartbeat_key(self.queue_name, worker_id)
        timeout = 5

        client.set(hb_key, "1", ex=_HEARTBEAT_TTL)

        stop_heartbeat = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(client, hb_key, stop_heartbeat),
            daemon=True,
            name=f"{self.worker_label}-heartbeat-{worker_id[:8]}",
        )
        heartbeat_thread.start()

        self._recover_orphaned_processing_queues(client, processing_queue_name)
        last_orphan_scan = time.monotonic()
        orphan_follow_ups_done = 0

        LOGGER.info(
            "[%s] Worker started (id=%s), listening on %s (processing list: %s)",
            self.worker_label,
            worker_id,
            self.queue_name,
            processing_queue_name,
        )
        try:
            while True:
                if self._drain_requested.is_set():
                    LOGGER.info("[%s] Drain requested, stopping worker", self.worker_label)
                    break
                try:
                    raw = client.brpoplpush(self.queue_name, processing_queue_name, timeout=timeout)
                    if self._drain_requested.is_set():
                        break
                    if raw is None:
                        if orphan_follow_ups_done < _MAX_ORPHAN_FOLLOW_UPS:
                            now = time.monotonic()
                            if now - last_orphan_scan >= _ORPHAN_FOLLOW_UP_DELAY:
                                self._recover_orphaned_processing_queues(client, processing_queue_name)
                                last_orphan_scan = now
                                orphan_follow_ups_done += 1
                        continue
                    data = raw
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError as e:
                        LOGGER.error("[%s] Invalid JSON from queue: %s", self.worker_label, e)
                        try:
                            client.lrem(processing_queue_name, 1, data)
                        except Exception as rm_exc:
                            LOGGER.exception(
                                "[%s] Failed to remove malformed item from processing list: %s",
                                self.worker_label,
                                rm_exc,
                            )
                        continue

                    missing_keys = [k for k in self.required_payload_keys if k not in payload]
                    if missing_keys:
                        LOGGER.error("[%s] Payload missing keys: %s", self.worker_label, ", ".join(missing_keys))
                        try:
                            client.lrem(processing_queue_name, 1, data)
                        except Exception as rm_exc:
                            LOGGER.exception(
                                "[%s] Failed to remove malformed item from processing list: %s",
                                self.worker_label,
                                rm_exc,
                            )
                        continue

                    try:
                        self.process_payload(payload, loop)
                    finally:
                        try:
                            client.lrem(processing_queue_name, 1, data)
                        except Exception as e:
                            LOGGER.exception(
                                "[%s] Failed to remove item from processing list (may be reprocessed on restart): %s",
                                self.worker_label,
                                e,
                            )
                except Exception as e:
                    LOGGER.exception("[%s] Worker error: %s", self.worker_label, e)
        finally:
            stop_heartbeat.set()
            try:
                client.delete(hb_key)
            except Exception:
                pass
            try:
                while True:
                    item = client.rpoplpush(processing_queue_name, self.queue_name)
                    if item is None:
                        break
                    LOGGER.info("[%s] Returned unprocessed item to main queue during shutdown", self.worker_label)
            except Exception as e:
                LOGGER.warning(
                    "[%s] Failed to return items from processing queue during shutdown: %s", self.worker_label, e,
                )
            self._cleanup_worker_keys(client, self.queue_name, worker_id)
            try:
                loop.close()
            except Exception:
                pass
