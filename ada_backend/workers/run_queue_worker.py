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
from uuid import UUID

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


def _process_run_payload(payload: dict) -> None:
    """Process one run from the queue: update RUNNING, run agent, update COMPLETED/FAILED, publish events."""
    _ensure_worker_trace_manager()
    run_id = UUID(payload["run_id"])
    project_id = UUID(payload["project_id"])
    env_str = payload["env"]
    input_data = payload["input_data"]
    response_format = ResponseFormat(payload.get("response_format", "s3_key"))

    try:
        env = EnvType(env_str)
    except ValueError:
        LOGGER.warning("Invalid env in run %s: %s", run_id, env_str)
        return

    session: Session = SessionLocal()
    try:
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
                call_type=CallType.API,
                response_format=response_format,
                event_callback=event_callback,
            )

        result = asyncio.run(execute_agent())
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
        update_run_status(
            session,
            run_id=run_id,
            project_id=project_id,
            status=RunStatus.FAILED,
            error={"message": str(e), "type": type(e).__name__},
            finished_at=datetime.now(timezone.utc),
        )
        publish_run_event(
            run_id,
            {"type": "run.failed", "error": {"message": str(e), "type": type(e).__name__}},
        )
    finally:
        session.close()


def _worker_loop() -> None:
    """Main BLPOP loop. Exits when drain is requested."""
    client = get_redis_client()
    if not client:
        LOGGER.warning("Redis client unavailable, run queue worker not starting")
        return
    queue_name = settings.REDIS_RUNS_QUEUE_NAME
    timeout = 5
    LOGGER.info("Run queue worker started, listening on %s", queue_name)
    while True:
        if _drain_requested.is_set():
            LOGGER.info("Drain requested, stopping run queue worker")
            break
        try:
            raw = client.blpop(queue_name, timeout=timeout)
            if _drain_requested.is_set():
                break
            if raw is None:
                continue
            _, data = raw
            try:
                payload = json.loads(data)
            except json.JSONDecodeError as e:
                LOGGER.error("Invalid JSON from run queue: %s", e)
                continue

            required_keys = ("run_id", "project_id", "env", "input_data")
            missing_keys = [key for key in required_keys if key not in payload]
            if missing_keys:
                LOGGER.error("Run queue payload missing keys: %s", ", ".join(missing_keys))
                continue

            _process_run_payload(payload)
        except Exception as e:
            LOGGER.exception("Run queue worker error: %s", e)


def start_run_queue_worker_thread() -> threading.Thread | None:
    """Start the BLPOP worker in a daemon thread. Returns the thread or None if Redis unavailable."""
    if not get_redis_client():
        return None
    t = threading.Thread(target=_worker_loop, daemon=True, name="run-queue-worker")
    t.start()
    return t
