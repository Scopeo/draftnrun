"""
BLPOP worker for async runs queue. Runs in a background thread per API process.
Pops run tasks from Redis, executes the agent with event_callback that publishes
to Redis Pub/Sub run:{run_id}, then updates Run status and publishes run.completed/run.failed.
"""

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, EnvType, ResponseFormat, RunStatus
from ada_backend.database.setup_db import SessionLocal
from ada_backend.repositories import run_repository
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.services.run_service import _upload_result_to_s3, update_run_status
from ada_backend.utils.redis_client import get_redis_client, publish_run_event
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from settings import settings

LOGGER = logging.getLogger(__name__)

# How long the heartbeat key lives in Redis without a refresh (seconds).
_HEARTBEAT_TTL = 60
# How often the heartbeat thread refreshes the key (seconds).
_HEARTBEAT_INTERVAL = 20

# Trace manager for the worker thread (ContextVar is thread-local, so we set it before each run).
_worker_trace_manager: TraceManager | None = None


def _ensure_worker_trace_manager() -> None:
    """Set trace manager in the current thread so get_trace_manager() returns it when building the agent."""
    global _worker_trace_manager
    if _worker_trace_manager is None:
        _worker_trace_manager = TraceManager(project_name="ada-backend-worker")
    set_trace_manager(_worker_trace_manager)


# Set by main on SIGTERM so the worker stops taking new work (drain).
_drain_requested = threading.Event()


def _request_drain() -> None:
    _drain_requested.set()


def _process_run_payload(payload: dict, loop: asyncio.AbstractEventLoop) -> None:
    """Process one run from the queue: update RUNNING, run agent, update COMPLETED/FAILED, publish events."""
    _ensure_worker_trace_manager()
    run_id = UUID(payload["run_id"])
    project_id = UUID(payload["project_id"])
    env_str = payload["env"]
    input_data = payload["input_data"]
    response_format = ResponseFormat(payload.get("response_format") or "s3_key")
    trigger_str = payload.get("trigger", CallType.API.value)

    session: Session = SessionLocal()
    try:
        try:
            env = EnvType(env_str)
        except ValueError as e:
            LOGGER.warning("Invalid env in run %s: %s", run_id, env_str)
            raise e

        try:
            call_type = CallType(trigger_str)
        except ValueError:
            LOGGER.warning("Invalid trigger in run %s: %s, defaulting to API", run_id, trigger_str)
            call_type = CallType.API

        run = run_repository.get_run(session, run_id)
        if not run:
            LOGGER.warning("Run %s not found, skipping", run_id)
            return
        current = run.status if isinstance(run.status, RunStatus) else RunStatus(str(run.status))
        if current != RunStatus.PENDING:
            LOGGER.debug("Run %s already %s, skipping", run_id, current)
            return

        now = datetime.now(timezone.utc)
        update_run_status(
            session,
            run_id=run_id,
            project_id=project_id,
            status=RunStatus.RUNNING,
            started_at=now,
        )

        async def event_callback(evt: dict):
            publish_run_event(run_id, evt)

        async def execute_agent():
            return await run_env_agent(
                session=session,
                project_id=project_id,
                env=env,
                input_data=input_data,
                call_type=call_type,
                response_format=response_format,
                event_callback=event_callback,
            )

        # Use the long-lived event loop for this worker thread.
        result = loop.run_until_complete(execute_agent())
        result_id = _upload_result_to_s3(result, project_id=project_id, run_id=run_id)
        update_run_status(
            session,
            run_id=run_id,
            project_id=project_id,
            status=RunStatus.COMPLETED,
            trace_id=result.trace_id,
            result_id=result_id,
            finished_at=datetime.now(timezone.utc),
        )
        publish_run_event(
            run_id,
            {"type": "run.completed", "trace_id": result.trace_id, "result_id": result_id},
        )
        LOGGER.info("Run %s completed", run_id)
    except Exception as e:
        LOGGER.exception("Run %s failed: %s", run_id, e)
        try:
            update_run_status(
                session,
                run_id=run_id,
                project_id=project_id,
                status=RunStatus.FAILED,
                error={"message": str(e), "type": type(e).__name__},
                finished_at=datetime.now(timezone.utc),
            )
        except Exception as status_exc:
            LOGGER.exception("Failed to update run %s to FAILED: %s", run_id, status_exc)

        try:
            publish_run_event(
                run_id,
                {"type": "run.failed", "error": {"message": str(e), "type": type(e).__name__}},
            )
        except Exception as event_exc:
            LOGGER.exception("Failed to publish run.failed event for %s: %s", run_id, event_exc)
    finally:
        session.close()


def _heartbeat_loop(client, heartbeat_key: str, stop_event: threading.Event) -> None:
    """Refresh the worker's heartbeat TTL periodically so it doesn't expire while the worker is alive."""
    while not stop_event.wait(timeout=_HEARTBEAT_INTERVAL):
        try:
            client.set(heartbeat_key, "1", ex=_HEARTBEAT_TTL)
        except Exception as e:
            LOGGER.warning("Failed to refresh worker heartbeat %s: %s", heartbeat_key, e)


def _recover_orphaned_processing_queues(client, queue_name: str, own_processing_queue: str) -> None:
    """Move items from processing queues that belong to dead workers back to the main queue.

    Each worker owns a uniquely-named processing queue keyed by its worker UUID and keeps a
    heartbeat key alive in Redis. A processing queue is considered orphaned — and therefore
    safe to recover — only when its corresponding heartbeat key has expired, which means the
    worker that owned it is no longer running.
    """
    try:
        pattern = f"{queue_name}:processing:*"
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match=pattern, count=100)
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                if key_str == own_processing_queue:
                    continue

                prefix = f"{queue_name}:processing:"
                orphan_worker_id = key_str[len(prefix):]
                heartbeat_key = f"{queue_name}:worker:{orphan_worker_id}:alive"

                if client.exists(heartbeat_key):
                    # Worker is still alive — do not touch its processing queue.
                    continue

                LOGGER.info("Recovering orphaned processing queue for dead worker %s", orphan_worker_id)
                while True:
                    item = client.rpoplpush(key_str, queue_name)
                    if item is None:
                        break
                    try:
                        payload = json.loads(item)
                        run_id = UUID(payload["run_id"])
                    except Exception:
                        try:
                            client.lrem(queue_name, 1, item)
                        except Exception as rm_exc:
                            LOGGER.exception(
                                "Failed to remove malformed item from main queue during orphan recovery: %s",
                                rm_exc,
                            )
                        continue

                    session: Session = SessionLocal()
                    try:
                        run = run_repository.get_run(session, run_id)
                        if not run:
                            continue
                        current = run.status if isinstance(run.status, RunStatus) else RunStatus(str(run.status))
                        if current == RunStatus.RUNNING:
                            # Bypass normal status transition validation: this run was in-flight
                            # when its worker died, so it is safe to reset it to PENDING for retry.
                            run_repository.update_run_status(
                                session,
                                run_id=run_id,
                                status=RunStatus.PENDING,
                            )
                    except Exception as e:
                        LOGGER.exception("Error resetting stuck RUNNING run %s to PENDING: %s", run_id, e)
                    finally:
                        session.close()

            if cursor == 0:
                break
    except Exception as e:
        LOGGER.exception("Error recovering orphaned processing queues: %s", e)


def _worker_loop() -> None:
    """Main worker loop using a per-worker processing list for safe concurrent restarts.

    Pattern:
    - Each worker generates a unique ID and owns ``{queue}:processing:{worker_id}``.
    - A heartbeat key ``{queue}:worker:{worker_id}:alive`` is refreshed every
      ``_HEARTBEAT_INTERVAL`` seconds with a TTL of ``_HEARTBEAT_TTL`` seconds.
    - On startup the worker scans all ``{queue}:processing:*`` keys and recovers
      only those whose heartbeat has expired (i.e. whose owner is dead).
    - Items being processed by other live workers are never touched.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client = get_redis_client()
    if not client:
        LOGGER.warning("Redis client unavailable, run queue worker not starting")
        return

    queue_name = settings.REDIS_RUNS_QUEUE_NAME
    worker_id = str(uuid4())
    processing_queue_name = f"{queue_name}:processing:{worker_id}"
    heartbeat_key = f"{queue_name}:worker:{worker_id}:alive"
    timeout = 5

    # Publish heartbeat before recovery so this worker is never mistaken for a dead one.
    client.set(heartbeat_key, "1", ex=_HEARTBEAT_TTL)

    stop_heartbeat = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(client, heartbeat_key, stop_heartbeat),
        daemon=True,
        name=f"run-queue-worker-heartbeat-{worker_id[:8]}",
    )
    heartbeat_thread.start()

    _recover_orphaned_processing_queues(client, queue_name, processing_queue_name)

    LOGGER.info(
        "Run queue worker started (id=%s), listening on %s (processing list: %s)",
        worker_id,
        queue_name,
        processing_queue_name,
    )
    try:
        while True:
            if _drain_requested.is_set():
                LOGGER.info("Drain requested, stopping run queue worker")
                break
            try:
                raw = client.brpoplpush(queue_name, processing_queue_name, timeout=timeout)
                if _drain_requested.is_set():
                    break
                if raw is None:
                    continue
                data = raw
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError as e:
                    LOGGER.error("Invalid JSON from run queue: %s", e)
                    try:
                        client.lrem(processing_queue_name, 1, data)
                    except Exception as rm_exc:
                        LOGGER.exception(
                            "Failed to remove malformed item from processing list: %s", rm_exc
                        )
                    continue

                required_keys = ("run_id", "project_id", "env", "input_data")
                missing_keys = [key for key in required_keys if key not in payload]
                if missing_keys:
                    LOGGER.error("Run queue payload missing keys: %s", ", ".join(missing_keys))
                    try:
                        client.lrem(processing_queue_name, 1, data)
                    except Exception as rm_exc:
                        LOGGER.exception(
                            "Failed to remove malformed item from processing list: %s", rm_exc
                        )
                    continue

                try:
                    _process_run_payload(payload, loop)
                finally:
                    try:
                        client.lrem(processing_queue_name, 1, data)
                    except Exception as e:
                        LOGGER.exception(
                            "Failed to remove run from processing list (may be reprocessed on restart): %s",
                            e,
                        )
            except Exception as e:
                LOGGER.exception("Run queue worker error: %s", e)
    finally:
        stop_heartbeat.set()
        try:
            # Delete the heartbeat immediately so other workers can recover our queue without
            # waiting for the TTL to expire if this process is restarting on the same host.
            client.delete(heartbeat_key)
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass


def start_run_queue_worker_thread() -> threading.Thread | None:
    """Start the BLPOP worker in a daemon thread. Returns the thread or None if Redis unavailable."""
    if not get_redis_client():
        return None
    t = threading.Thread(target=_worker_loop, daemon=True, name="run-queue-worker")
    t.start()
    return t
