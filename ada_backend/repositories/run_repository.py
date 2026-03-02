from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def create_run(
    session: Session,
    project_id: UUID,
    input_payload: Optional[dict] = None,
    trigger: db.CallType = db.CallType.API,
) -> db.Run:
    """Create a new run with status pending. Caller manages transaction."""
    run = db.Run(
        project_id=project_id,
        status=db.RunStatus.PENDING,
        trigger=trigger,
        input_payload=input_payload or {},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_run(session: Session, run_id: UUID) -> Optional[db.Run]:
    return session.query(db.Run).filter(db.Run.id == run_id).first()


def update_run_status(
    session: Session,
    run_id: UUID,
    status: db.RunStatus,
    error: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Optional[db.Run]:
    """Update run status and optionally error/trace_id. Returns updated run or None if not found."""
    run = get_run(session, run_id)
    if run is None:
        return None
    run.status = status
    if error is not None:
        run.error = error
    if trace_id is not None:
        run.trace_id = trace_id
    session.commit()
    session.refresh(run)
    return run
