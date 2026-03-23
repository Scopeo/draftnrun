import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import QASession, RunStatus

LOGGER = logging.getLogger(__name__)


def create_qa_session(
    session: Session,
    *,
    project_id: UUID,
    dataset_id: UUID,
    graph_runner_id: UUID,
) -> QASession:
    qa_session = QASession(
        project_id=project_id,
        dataset_id=dataset_id,
        graph_runner_id=graph_runner_id,
        status=RunStatus.PENDING,
    )
    session.add(qa_session)
    session.commit()
    session.refresh(qa_session)
    return qa_session


def get_qa_session(session: Session, qa_session_id: UUID) -> Optional[QASession]:
    return session.query(QASession).filter(QASession.id == qa_session_id).first()


def get_qa_sessions_by_project(
    session: Session,
    project_id: UUID,
    dataset_id: Optional[UUID] = None,
) -> list[QASession]:
    query = (
        session.query(QASession)
        .filter(QASession.project_id == project_id)
        .order_by(QASession.created_at.desc())
    )
    if dataset_id:
        query = query.filter(QASession.dataset_id == dataset_id)
    return query.all()


def update_qa_session_status(
    session: Session,
    qa_session_id: UUID,
    *,
    status: RunStatus,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
    total: Optional[int] = None,
    passed: Optional[int] = None,
    failed: Optional[int] = None,
    error: Optional[dict] = None,
) -> Optional[QASession]:
    qa_session = get_qa_session(session, qa_session_id)
    if not qa_session:
        LOGGER.error(f"QASession {qa_session_id} not found for status update")
        return None
    qa_session.status = status
    if started_at is not None:
        qa_session.started_at = started_at
    if finished_at is not None:
        qa_session.finished_at = finished_at
    if total is not None:
        qa_session.total = total
    if passed is not None:
        qa_session.passed = passed
    if failed is not None:
        qa_session.failed = failed
    if error is not None:
        qa_session.error = error
    session.commit()
    session.refresh(qa_session)
    return qa_session
