import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, RunStatus
from ada_backend.database.setup_db import get_db_session
from ada_backend.mixpanel_analytics import track_run_completed
from ada_backend.repositories import run_repository
from ada_backend.repositories.project_repository import get_project
from ada_backend.repositories.run_input_repository import get_run_input
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.run_schema import AsyncRunAcceptedSchema, RunResponseSchema
from ada_backend.services.alerting.alert_service import maybe_send_run_failure_alert
from ada_backend.services.agent_runner_service import setup_tracing_context
from ada_backend.services.errors import (
    InvalidRunStatusTransition,
    ProjectNotFound,
    ResultsBucketNotConfigured,
    RunNotFound,
    RunResultNotFound,
)
from ada_backend.services.s3_files_service import get_s3_client_and_ensure_bucket
from ada_backend.utils.redis_client import push_run_task
from data_ingestion.boto3_client import get_content_from_file, upload_file_to_bucket
from engine.trace.span_context import set_tracing_span
from settings import settings

LOGGER = logging.getLogger(__name__)

# Allowed run status transitions: status cannot go backwards (PENDING -> RUNNING -> COMPLETED/FAILED).
_VALID_RUN_STATUS_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset(),  # terminal
    RunStatus.FAILED: frozenset(),  # terminal
}


def _upload_result_to_s3(
    result: ChatResponse, project_id: UUID, run_id: UUID, bucket_name: str = settings.RESULTS_S3_BUCKET_NAME
) -> Optional[str]:
    """
    Serialize the ChatResponse to JSON and upload it to the results S3 bucket.
    Returns the S3 key on success, or None if the bucket is not configured or upload fails.
    """
    if not bucket_name:
        LOGGER.warning(
            "RESULTS_S3_BUCKET_NAME is not configured — skipping result upload. "
            "Set it in your credentials.env to persist run results."
        )
        return None
    try:
        s3_key = f"results/{project_id}/{run_id}.json"
        payload = result.model_dump_json().encode("utf-8")
        s3_client = get_s3_client_and_ensure_bucket(bucket_name=bucket_name)
        upload_file_to_bucket(
            s3_client=s3_client,
            bucket_name=bucket_name,
            key=s3_key,
            byte_content=payload,
        )
        LOGGER.info(f"Uploaded run result to S3: {s3_key}")
        return s3_key
    except Exception:
        LOGGER.exception(f"Failed to upload run result to S3 for run {run_id}")
        return None


async def run_with_tracking(
    project_id: UUID,
    trigger: CallType,
    runner_coro: Awaitable[ChatResponse],
    webhook_id: UUID | None = None,
    integration_trigger_id: UUID | None = None,
    run_id: UUID | None = None,
    event_id: str | None = None,
) -> ChatResponse:
    """
    Create a run record (or use existing run_id), set it to RUNNING, execute the runner coroutine,
    then set COMPLETED (with result) or FAILED (with error).
    When run_id is provided (e.g. after returning 202), the run row must already exist; no new run is created.

    Each DB operation uses its own short-lived session so that no connection is held
    during the (potentially long-running) runner coroutine.
    """
    with get_db_session() as session:
        if run_id is None:
            run = create_run(
                session,
                project_id=project_id,
                trigger=trigger,
                webhook_id=webhook_id,
                integration_trigger_id=integration_trigger_id,
                event_id=event_id,
            )
            run_id = run.id
        set_tracing_span(run_id=str(run_id))
        now = datetime.now(timezone.utc)
        update_run_status(
            session,
            run_id=run_id,
            project_id=project_id,
            status=RunStatus.RUNNING,
            started_at=now,
        )
    try:
        result = await runner_coro
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - now).total_seconds() * 1000)
        result_id = _upload_result_to_s3(result, project_id=project_id, run_id=run_id)
        with get_db_session() as session:
            update_run_status(
                session,
                run_id=run_id,
                project_id=project_id,
                status=RunStatus.COMPLETED,
                trace_id=result.trace_id,
                result_id=result_id,
                finished_at=finished_at,
            )
        track_run_completed(
            user_id=None,
            project_id=project_id,
            status="completed",
            trigger=trigger.value,
            duration_ms=duration_ms,
        )
        return result
    except Exception as e:
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - now).total_seconds() * 1000)
        trace_id = getattr(e, "trace_id", None)
        try:
            with get_db_session() as session:
                update_run_status(
                    session,
                    run_id=run_id,
                    project_id=project_id,
                    status=RunStatus.FAILED,
                    error={"message": str(e), "type": type(e).__name__},
                    trace_id=trace_id,
                    finished_at=finished_at,
                )
        except Exception:
            LOGGER.exception("Failed to persist FAILED status: run_id=%s project_id=%s", run_id, project_id)
        LOGGER.exception(
            "Run failed: run_id=%s project_id=%s duration_ms=%s trace_id=%s",
            run_id,
            project_id,
            duration_ms,
            trace_id,
        )
        track_run_completed(
            user_id=None,
            project_id=project_id,
            status="failed",
            trigger=trigger.value,
            duration_ms=duration_ms,
        )
        raise


def get_run_final_state_event(session: Session, run_id: UUID) -> Optional[Dict[str, Any]]:
    """
    If the run is already completed or failed, return the event dict to send over WebSocket
    (run.completed or run.failed). Returns None if run not found or still pending/running.
    Used when a client connects to the run stream after the run has finished.
    """
    run = run_repository.get_run(session, run_id)
    if not run:
        return None
    try:
        session.refresh(run)
    except Exception:
        session.expire(run)
    status = run.status if isinstance(run.status, RunStatus) else RunStatus(str(run.status))
    if status == RunStatus.COMPLETED:
        return {
            "type": "run.completed",
            "trace_id": getattr(run, "trace_id", None),
            "result_id": getattr(run, "result_id", None),
        }
    if status == RunStatus.FAILED:
        return {
            "type": "run.failed",
            "error": getattr(run, "error", None) or {"message": "Run failed", "type": "UnknownError"},
        }
    return None


async def stream_run_events(
    session: Session,
    run_id: UUID,
    queue: asyncio.Queue,
    *,
    ping_timeout_seconds: int = 25,
) -> AsyncIterator[str]:
    """
    Async generator that yields JSON messages to send over the run WebSocket stream.
    First yields the final state event (run.completed / run.failed) if the run is already done,
    then yields events from the queue (node.started, node.completed, run.completed, run.failed)
    until a terminal event or timeout. Caller sends each yielded string to the WebSocket.
    """
    final_state = get_run_final_state_event(session, run_id)
    if final_state is not None:
        yield json.dumps(final_state)
        return
    while True:
        try:
            data = await asyncio.wait_for(queue.get(), timeout=ping_timeout_seconds)
        except asyncio.TimeoutError:
            final_state = get_run_final_state_event(session, run_id)
            if final_state is not None:
                yield json.dumps(final_state)
                return
            yield json.dumps({"type": "ping"})
            continue
        yield data if isinstance(data, str) else json.dumps(data)
        try:
            evt = json.loads(data) if isinstance(data, str) else data
            if isinstance(evt, dict) and evt.get("type") in ("run.completed", "run.failed"):
                return
        except (json.JSONDecodeError, TypeError):
            pass


def create_run(
    session: Session,
    project_id: UUID,
    trigger: CallType = CallType.API,
    webhook_id: UUID | None = None,
    integration_trigger_id: UUID | None = None,
    attempt_number: int = 1,
    event_id: str | None = None,
    retry_group_id: UUID | None = None,
) -> RunResponseSchema:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ProjectNotFound(project_id)
    run = run_repository.create_run(
        session,
        project_id=project_id,
        trigger=trigger,
        webhook_id=webhook_id,
        integration_trigger_id=integration_trigger_id,
        event_id=event_id,
        attempt_number=attempt_number,
        retry_group_id=retry_group_id,
    )
    return RunResponseSchema.model_validate(run, from_attributes=True)


def get_run(session: Session, run_id: UUID, project_id: UUID) -> RunResponseSchema:
    run = run_repository.get_run(session, run_id)
    if not run:
        raise RunNotFound(run_id)
    if run.project_id != project_id:
        raise RunNotFound(run_id)
    return RunResponseSchema.model_validate(run, from_attributes=True)


def get_run_result(session: Session, run_id: UUID, project_id: UUID) -> ChatResponse:
    """
    Fetch the run's result (ChatResponse) from S3. Run must exist and belong to project.
    Raises RunNotFound if run missing or wrong project; RunResultNotFound if no result_id;
    ResultsBucketNotConfigured if bucket not set; ValueError if S3 get fails.
    """
    run_schema = get_run(session, run_id=run_id, project_id=project_id)
    result_id = run_schema.result_id
    if not result_id:
        raise RunResultNotFound(run_id)
    bucket_name = settings.RESULTS_S3_BUCKET_NAME
    if not bucket_name:
        raise ResultsBucketNotConfigured()
    s3_client = get_s3_client_and_ensure_bucket(bucket_name=bucket_name)
    content = get_content_from_file(s3_client, bucket_name=bucket_name, key=result_id)
    data = json.loads(content.decode("utf-8"))
    return ChatResponse.model_validate(data)


def get_runs(
    session: Session,
    project_id: UUID,
    page: int = 1,
    page_size: int = 50,
) -> tuple[List[RunResponseSchema], int]:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ProjectNotFound(project_id)
    total = run_repository.count_runs_by_project(session, project_id=project_id)
    offset = (page - 1) * page_size
    runs = run_repository.get_runs_by_project(session, project_id=project_id, limit=page_size, offset=offset)
    items = [RunResponseSchema.model_validate(r, from_attributes=True) for r in runs]
    return items, total


def fail_pending_run(
    session: Session,
    run_id: UUID,
    error: dict,
    project_id: UUID | None = None,
) -> RunResponseSchema:
    finished_at = datetime.now(timezone.utc)
    updated = run_repository.fail_run_if_pending(
        session,
        run_id=run_id,
        error=error,
        finished_at=finished_at,
        project_id=project_id,
    )
    if updated is None:
        run = run_repository.get_run(session, run_id)
        if not run:
            raise RunNotFound(run_id)
        if project_id is not None and run.project_id != project_id:
            raise RunNotFound(run_id)
        current = run.status if isinstance(run.status, RunStatus) else RunStatus(str(run.status))
        raise InvalidRunStatusTransition(current.value, RunStatus.FAILED.value)
    maybe_send_run_failure_alert(updated, updated.project_id, error=error, finished_at=finished_at)
    return RunResponseSchema.model_validate(updated, from_attributes=True)


def update_run_status(
    session: Session,
    run_id: UUID,
    project_id: UUID,
    status: RunStatus,
    error: Optional[dict] = None,
    trace_id: Optional[str] = None,
    result_id: Optional[str] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> RunResponseSchema:
    run = run_repository.get_run(session, run_id)
    if not run:
        raise RunNotFound(run_id)
    if run.project_id != project_id:
        raise RunNotFound(run_id)
    current = run.status if isinstance(run.status, RunStatus) else RunStatus(str(run.status))
    allowed = _VALID_RUN_STATUS_TRANSITIONS.get(current, frozenset())
    if status != current and status not in allowed:
        raise InvalidRunStatusTransition(current.value, status.value)
    now = datetime.now(timezone.utc)
    if started_at is None and status == RunStatus.RUNNING:
        started_at = now
    if finished_at is None and status in (RunStatus.COMPLETED, RunStatus.FAILED):
        finished_at = now
    updated = run_repository.update_run_status(
        session,
        run_id=run_id,
        status=status,
        error=error,
        trace_id=trace_id,
        result_id=result_id,
        started_at=started_at,
        finished_at=finished_at,
    )
    if status == RunStatus.FAILED:
        maybe_send_run_failure_alert(run, project_id, error=error, finished_at=finished_at)
    return RunResponseSchema.model_validate(updated, from_attributes=True)


def retry_run(
    session: Session,
    run_id: UUID,
    project_id: UUID,
    env: str | None = None,
    graph_runner_id: UUID | None = None,
) -> AsyncRunAcceptedSchema:
    if env is None and graph_runner_id is None:
        raise ValueError("Either env or graph_runner_id must be provided")

    run = run_repository.get_run(session, run_id)
    if not run or run.project_id != project_id:
        raise RunNotFound(run_id)

    retry_group_id = run.retry_group_id or run.id
    input_data = get_run_input(session, retry_group_id=retry_group_id)
    if input_data is None:
        raise ValueError("Run input not found for retry")

    latest_attempt = run_repository.get_latest_run_by_retry_group(session, retry_group_id=retry_group_id)
    next_attempt = (latest_attempt.attempt_number if latest_attempt is not None else run.attempt_number) + 1

    retried_run = create_run(
        session=session,
        project_id=project_id,
        trigger=run.trigger,
        webhook_id=run.webhook_id,
        integration_trigger_id=run.integration_trigger_id,
        event_id=run.event_id,
        retry_group_id=retry_group_id,
        attempt_number=next_attempt,
    )

    setup_tracing_context(session=session, project_id=project_id)
    set_tracing_span(run_id=str(retried_run.id))

    pushed = push_run_task(
        run_id=retried_run.id,
        project_id=project_id,
        env=env,
        input_data=input_data,
        trigger=run.trigger.value,
        graph_runner_id=graph_runner_id,
    )
    if not pushed:
        update_run_status(
            session,
            run_id=retried_run.id,
            project_id=project_id,
            status=RunStatus.FAILED,
            error={"message": "Failed to enqueue run; Redis unavailable.", "type": "EnqueueError"},
        )
        raise ValueError("Retry run could not be enqueued")

    return AsyncRunAcceptedSchema(run_id=retried_run.id, status="pending")
