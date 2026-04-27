from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.schemas.run_schema import OrgRunResponseSchema

RUN_INPUT_RETENTION_DAYS = 7


def create_run(
    session: Session,
    project_id: UUID,
    trigger: db.CallType = db.CallType.API,
    webhook_id: UUID | None = None,
    integration_trigger_id: UUID | None = None,
    attempt_number: int = 1,
    event_id: str | None = None,
    retry_group_id: UUID | None = None,
    env: db.EnvType | None = None,
) -> db.Run:
    """Create a new run with status pending. Caller manages transaction."""
    run_id = uuid4()
    run_retry_group_id = retry_group_id or uuid4()
    kwargs: dict = {
        "id": run_id,
        "project_id": project_id,
        "status": db.RunStatus.PENDING,
        "trigger": trigger,
        "webhook_id": webhook_id,
        "integration_trigger_id": integration_trigger_id,
        "attempt_number": attempt_number,
        "retry_group_id": run_retry_group_id,
        "env": env,
    }
    if event_id is not None:
        kwargs["event_id"] = event_id
    run = db.Run(**kwargs)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_run(session: Session, run_id: UUID) -> Optional[db.Run]:
    return session.query(db.Run).filter(db.Run.id == run_id).first()


def get_latest_run_by_retry_group(session: Session, retry_group_id: UUID) -> Optional[db.Run]:
    return (
        session.query(db.Run)
        .filter(db.Run.retry_group_id == retry_group_id)
        .order_by(db.Run.attempt_number.desc(), db.Run.created_at.desc())
        .first()
    )


def _apply_run_filters(
    query,
    statuses: list[db.RunStatus] | None = None,
    project_ids: list[UUID] | None = None,
    triggers: list[db.CallType] | None = None,
    envs: list[db.EnvType] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    if statuses:
        query = query.filter(db.Run.status.in_(statuses))
    if project_ids:
        query = query.filter(db.Run.project_id.in_(project_ids))
    if triggers:
        query = query.filter(db.Run.trigger.in_(triggers))
    if envs:
        query = query.filter(db.Run.env.in_(envs))
    if date_from is not None:
        query = query.filter(db.Run.created_at >= date_from)
    if date_to is not None:
        query = query.filter(db.Run.created_at <= date_to)
    return query


def count_runs_by_organization(
    session: Session,
    organization_id: UUID,
    statuses: list[db.RunStatus] | None = None,
    project_ids: list[UUID] | None = None,
    triggers: list[db.CallType] | None = None,
    envs: list[db.EnvType] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> int:
    query = session.query(db.Run).join(db.Project, db.Run.project_id == db.Project.id)
    query = query.filter(db.Project.organization_id == organization_id)
    query = _apply_run_filters(
        query, statuses=statuses, project_ids=project_ids, triggers=triggers, envs=envs,
        date_from=date_from, date_to=date_to,
    )
    return query.count()


def get_runs_by_organization(
    session: Session,
    organization_id: UUID,
    limit: int = 50,
    offset: int = 0,
    statuses: list[db.RunStatus] | None = None,
    project_ids: list[UUID] | None = None,
    triggers: list[db.CallType] | None = None,
    envs: list[db.EnvType] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[OrgRunResponseSchema]:
    """Return runs for an org with project_name, attempt_count, and input_available."""
    retry_siblings = db.Run.__table__.alias("retry_siblings")
    attempt_count_expr = (
        select(func.max(retry_siblings.c.attempt_number))
        .select_from(retry_siblings)
        .where(retry_siblings.c.retry_group_id == db.Run.retry_group_id)
        .correlate(db.Run)
    ).scalar_subquery()

    cutoff = datetime.now(timezone.utc) - timedelta(days=RUN_INPUT_RETENTION_DAYS)
    input_available_expr = (
        select(func.count())
        .select_from(db.RunInput)
        .where(db.RunInput.retry_group_id == db.Run.retry_group_id, db.RunInput.created_at > cutoff)
        .correlate(db.Run)
    ).scalar_subquery()

    query = (
        session.query(
            db.Run,
            db.Project.name.label("project_name"),
            attempt_count_expr.label("attempt_count"),
            case((input_available_expr > 0, True), else_=False).label("input_available"),
        )
        .join(db.Project, db.Run.project_id == db.Project.id)
        .filter(db.Project.organization_id == organization_id)
    )
    query = _apply_run_filters(
        query, statuses=statuses, project_ids=project_ids, triggers=triggers, envs=envs,
        date_from=date_from, date_to=date_to,
    )

    rows = query.order_by(db.Run.created_at.desc()).limit(limit).offset(offset).all()

    return [
        OrgRunResponseSchema(
            id=run.id,
            project_id=run.project_id,
            project_name=project_name,
            status=run.status,
            trigger=run.trigger,
            env=run.env,
            trace_id=run.trace_id,
            error=run.error,
            retry_group_id=run.retry_group_id,
            attempt_number=run.attempt_number,
            attempt_count=attempt_count or 1,
            input_available=bool(input_available),
            started_at=run.started_at,
            finished_at=run.finished_at,
            created_at=run.created_at,
        )
        for run, project_name, attempt_count, input_available in rows
    ]


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
    stmt = update(db.Run).where(*conditions).values(status=db.RunStatus.FAILED, error=error, finished_at=finished_at)
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
