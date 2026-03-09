import logging
from datetime import datetime, timezone
from typing import Awaitable, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, RunStatus
from ada_backend.repositories import run_repository
from ada_backend.repositories.project_repository import get_project
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.run_schema import RunResponseSchema
from ada_backend.services.errors import InvalidRunStatusTransition, ProjectNotFound, RunNotFound
from ada_backend.services.s3_files_service import get_s3_client_and_ensure_bucket
from data_ingestion.boto3_client import upload_file_to_bucket
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
    session: Session,
    project_id: UUID,
    trigger: CallType,
    runner_coro: Awaitable[ChatResponse],
    webhook_id: UUID | None = None,
    integration_trigger_id: UUID | None = None,
    run_id: UUID | None = None,
) -> ChatResponse:
    """
    Create a run record (or use existing run_id), set it to RUNNING, execute the runner coroutine,
    then set COMPLETED (with result) or FAILED (with error).
    When run_id is provided (e.g. after returning 202), the run row must already exist; no new run is created.
    """
    if run_id is None:
        run = create_run(
            session,
            project_id=project_id,
            trigger=trigger,
            webhook_id=webhook_id,
            integration_trigger_id=integration_trigger_id,
        )
        run_id = run.id
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
        return result
    except Exception as e:
        update_run_status(
            session,
            run_id=run_id,
            project_id=project_id,
            status=RunStatus.FAILED,
            error={"message": str(e), "type": type(e).__name__},
            finished_at=datetime.now(timezone.utc),
        )
        raise


def create_run(
    session: Session,
    project_id: UUID,
    trigger: CallType = CallType.API,
    webhook_id: UUID | None = None,
    integration_trigger_id: UUID | None = None,
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
    )
    return RunResponseSchema.model_validate(run, from_attributes=True)


def get_run(session: Session, run_id: UUID, project_id: UUID) -> RunResponseSchema:
    run = run_repository.get_run(session, run_id)
    if not run:
        raise RunNotFound(run_id)
    if run.project_id != project_id:
        raise RunNotFound(run_id)
    return RunResponseSchema.model_validate(run, from_attributes=True)


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
    return RunResponseSchema.model_validate(updated, from_attributes=True)
