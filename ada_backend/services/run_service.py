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

# Allowed run status transitions: status cannot go backwards (PENDING -> RUNNING -> COMPLETED/FAILED).
_VALID_RUN_STATUS_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset(),  # terminal
    RunStatus.FAILED: frozenset(),  # terminal
}


async def run_with_tracking(
    session: Session,
    project_id: UUID,
    trigger: CallType,
    runner_coro: Awaitable[ChatResponse],
) -> ChatResponse:
    """
    Create a run record, set it to RUNNING, execute the runner coroutine,
    then set COMPLETED (with result) or FAILED (with error). Same pattern as cron's _execute_cron_job.
    """
    run = create_run(session, project_id=project_id, trigger=trigger)
    now = datetime.now(timezone.utc)
    update_run_status(
        session,
        run_id=run.id,
        project_id=project_id,
        status=RunStatus.RUNNING,
        started_at=now,
    )
    try:
        result = await runner_coro
        update_run_status(
            session,
            run_id=run.id,
            project_id=project_id,
            status=RunStatus.COMPLETED,
            trace_id=result.trace_id,
            finished_at=datetime.now(timezone.utc),
        )
        return result
    except Exception as e:
        update_run_status(
            session,
            run_id=run.id,
            project_id=project_id,
            status=RunStatus.FAILED,
            error=str(e),
            finished_at=datetime.now(timezone.utc),
        )
        raise


def create_run(
    session: Session,
    project_id: UUID,
    trigger: CallType = CallType.API,
) -> RunResponseSchema:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ProjectNotFound(project_id)
    run = run_repository.create_run(session, project_id=project_id, trigger=trigger)
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
    runs = run_repository.get_runs_by_project(
        session, project_id=project_id, limit=page_size, offset=offset
    )
    items = [RunResponseSchema.model_validate(r, from_attributes=True) for r in runs]
    return items, total


def update_run_status(
    session: Session,
    run_id: UUID,
    project_id: UUID,
    status: RunStatus,
    error: Optional[str] = None,
    trace_id: Optional[str] = None,
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
        started_at=started_at,
        finished_at=finished_at,
    )
    return RunResponseSchema.model_validate(updated, from_attributes=True)
