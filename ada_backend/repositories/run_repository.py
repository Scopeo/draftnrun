from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from ada_backend.database import models as db


def create_run(
    session: Session,
    project_id: UUID,
    trigger: db.CallType = db.CallType.API,
    webhook_id: UUID | None = None,
    integration_trigger_id: UUID | None = None,
    event_id: str | None = None,
) -> db.Run:
    """Create a new run with status pending. Caller manages transaction."""
    run = db.Run(
        project_id=project_id,
        status=db.RunStatus.PENDING,
        trigger=trigger,
        webhook_id=webhook_id,
        integration_trigger_id=integration_trigger_id,
        event_id=event_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_run(session: Session, run_id: UUID) -> Optional[db.Run]:
    return session.query(db.Run).filter(db.Run.id == run_id).first()


def count_runs_by_project(session: Session, project_id: UUID) -> int:
    """Return total number of runs for a project."""
    return session.query(db.Run).filter(db.Run.project_id == project_id).count()


def get_runs_by_project(
    session: Session,
    project_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> List[db.Run]:
    """Return runs for a project, newest first."""
    return (
        session.query(db.Run)
        .filter(db.Run.project_id == project_id)
        .order_by(db.Run.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def fail_run_if_pending(
    session: Session,
    run_id: UUID,
    error: dict,
    finished_at: datetime,
    project_id: UUID | None = None,
) -> Optional[db.Run]:
    """Atomically transition a PENDING run to FAILED. Returns None if no row matched."""
    conditions = [db.Run.id == run_id, db.Run.status == db.RunStatus.PENDING]
    if project_id is not None:
        conditions.append(db.Run.project_id == project_id)
    stmt = (
        update(db.Run)
        .where(*conditions)
        .values(status=db.RunStatus.FAILED, error=error, finished_at=finished_at)
    )
    result = session.execute(stmt)
    if result.rowcount == 0:
        return None
    session.commit()
    return get_run(session, run_id)


def update_run_status(
    session: Session,
    run_id: UUID,
    status: db.RunStatus,
    error: Optional[dict] = None,
    trace_id: Optional[str] = None,
    result_id: Optional[str] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> Optional[db.Run]:
    """Update run status and optionally error/trace_id/result_id/started_at/finished_at."""
    run = get_run(session, run_id)
    if run is None:
        return None
    run.status = status
    if error is not None:
        run.error = error
    if trace_id is not None:
        run.trace_id = trace_id
    if result_id is not None:
        run.result_id = result_id
    if started_at is not None:
        run.started_at = started_at
    if finished_at is not None:
        run.finished_at = finished_at
    session.commit()
    session.refresh(run)
    return run
