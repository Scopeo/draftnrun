import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def get_cron_job(
    session: Session,
    cron_id: UUID,
) -> Optional[db.CronJob]:
    return session.query(db.CronJob).filter(db.CronJob.id == cron_id, db.CronJob.deleted_at.is_(None)).first()


def get_cron_jobs_by_organization(
    session: Session,
    organization_id: UUID,
    enabled_only: bool = False,
) -> List[db.CronJob]:
    query = session.query(db.CronJob).filter(
        db.CronJob.organization_id == organization_id, db.CronJob.deleted_at.is_(None)
    )

    if enabled_only:
        query = query.filter(db.CronJob.is_enabled.is_(True))

    return query.order_by(desc(db.CronJob.created_at)).all()


def get_cron_runs_by_cron_id(
    session: Session,
    cron_id: UUID,
    limit: Optional[int] = None,
) -> List[db.CronRun]:
    query = session.query(db.CronRun).filter(db.CronRun.cron_id == cron_id)
    query = query.order_by(desc(db.CronRun.scheduled_for))

    if limit:
        query = query.limit(limit)

    return query.all()


def get_all_enabled_cron_jobs(session: Session) -> List[db.CronJob]:
    return session.query(db.CronJob).filter(db.CronJob.is_enabled.is_(True), db.CronJob.deleted_at.is_(None)).all()


def insert_cron_job(
    session: Session,
    cron_id: UUID,
    organization_id: UUID,
    name: str,
    cron_expr: str,
    tz: str,
    entrypoint: str,
    payload: dict,
    is_enabled: bool = True,
) -> db.CronJob:
    cron_job = db.CronJob(
        id=cron_id,
        organization_id=organization_id,
        name=name,
        cron_expr=cron_expr,
        tz=tz,
        entrypoint=entrypoint,
        payload=payload,
        is_enabled=is_enabled,
    )
    session.add(cron_job)
    session.commit()
    session.refresh(cron_job)
    return cron_job


def update_cron_job(
    session: Session,
    cron_id: UUID,
    name: Optional[str] = None,
    cron_expr: Optional[str] = None,
    tz: Optional[str] = None,
    entrypoint: Optional[str] = None,
    payload: Optional[dict] = None,
    is_enabled: Optional[bool] = None,
) -> Optional[db.CronJob]:
    cron_job = session.query(db.CronJob).filter(db.CronJob.id == cron_id).first()

    if not cron_job:
        return None

    if name is not None:
        cron_job.name = name
    if cron_expr is not None:
        cron_job.cron_expr = cron_expr
    if tz is not None:
        cron_job.tz = tz
    if entrypoint is not None:
        cron_job.entrypoint = entrypoint
    if payload is not None:
        cron_job.payload = payload
    if is_enabled is not None:
        cron_job.is_enabled = is_enabled

    session.commit()
    session.refresh(cron_job)
    return cron_job


def delete_cron_job(session: Session, cron_id: UUID) -> bool:
    cron_job = session.query(db.CronJob).filter(db.CronJob.id == cron_id, db.CronJob.deleted_at.is_(None)).first()

    if not cron_job:
        return False

    cron_job.deleted_at = datetime.utcnow()
    session.commit()
    return True


def insert_cron_run(
    session: Session,
    cron_id: UUID,
    scheduled_for: datetime,
    started_at: datetime,
    status: db.CronStatus,
    finished_at: Optional[datetime] = None,
    error: Optional[str] = None,
) -> db.CronRun:
    cron_run = db.CronRun(
        cron_id=cron_id,
        scheduled_for=scheduled_for,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        error=error,
    )
    session.add(cron_run)
    session.commit()
    session.refresh(cron_run)
    return cron_run


def update_cron_run(
    session: Session,
    run_id: UUID,
    status: Optional[db.CronStatus] = None,
    finished_at: Optional[datetime] = None,
    error: Optional[str] = None,
    result: Optional[dict] = None,
) -> Optional[db.CronRun]:
    cron_run = session.query(db.CronRun).filter(db.CronRun.id == run_id).first()

    if not cron_run:
        return None

    if status is not None:
        cron_run.status = status
    if finished_at is not None:
        cron_run.finished_at = finished_at
    if error is not None:
        cron_run.error = error
    if result is not None:
        cron_run.result = result

    session.commit()
    session.refresh(cron_run)
    return cron_run
