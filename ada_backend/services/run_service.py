from typing import Awaitable, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, RunStatus
from ada_backend.repositories.project_repository import get_project
from ada_backend.repositories.run_repository import create_run as repo_create_run
from ada_backend.repositories.run_repository import get_run as repo_get_run
from ada_backend.repositories.run_repository import update_run_status as repo_update_run_status
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.run_schema import RunResponseSchema
from ada_backend.services.errors import ProjectNotFound, RunNotFound


async def run_with_tracking(
    session: Session,
    project_id: UUID,
    trigger: CallType,
    input_payload: Optional[dict],
    runner_coro: Awaitable[ChatResponse],
) -> ChatResponse:
    """
    Create a run record, set it to RUNNING, execute the runner coroutine,
    then set COMPLETED (with result) or FAILED (with error). Same pattern as cron's _execute_cron_job.
    """
    run = create_run(
        session, project_id=project_id, input_payload=input_payload, trigger=trigger
    )
    update_run_status(
        session, run_id=run.id, project_id=project_id, status=RunStatus.RUNNING
    )
    try:
        result = await runner_coro
        update_run_status(
            session,
            run_id=run.id,
            project_id=project_id,
            status=RunStatus.COMPLETED,
            trace_id=result.trace_id,
        )
        return result
    except Exception as e:
        update_run_status(
            session,
            run_id=run.id,
            project_id=project_id,
            status=RunStatus.FAILED,
            error=str(e),
        )
        raise


def create_run(
    session: Session,
    project_id: UUID,
    input_payload: Optional[dict] = None,
    trigger: CallType = CallType.API,
) -> RunResponseSchema:
    project = get_project(session, project_id=project_id)
    if not project:
        raise ProjectNotFound(project_id)
    run = repo_create_run(session, project_id=project_id, input_payload=input_payload, trigger=trigger)
    return RunResponseSchema.model_validate(run, from_attributes=True)


def get_run(session: Session, run_id: UUID, project_id: UUID) -> RunResponseSchema:
    run = repo_get_run(session, run_id)
    if not run:
        raise RunNotFound(run_id)
    if run.project_id != project_id:
        raise RunNotFound(run_id)
    return RunResponseSchema.model_validate(run, from_attributes=True)


def update_run_status(
    session: Session,
    run_id: UUID,
    project_id: UUID,
    status: RunStatus,
    error: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> RunResponseSchema:
    run = repo_get_run(session, run_id)
    if not run:
        raise RunNotFound(run_id)
    if run.project_id != project_id:
        raise RunNotFound(run_id)
    updated = repo_update_run_status(
        session, run_id=run_id, status=status, error=error, trace_id=trace_id
    )
    return RunResponseSchema.model_validate(updated, from_attributes=True)
