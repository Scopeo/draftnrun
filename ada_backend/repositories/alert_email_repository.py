from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.services.errors import DuplicateAlertEmailError


def list_alert_emails_by_project(session: Session, project_id: UUID) -> list[db.ProjectAlertEmail]:
    return (
        session.query(db.ProjectAlertEmail)
        .filter(db.ProjectAlertEmail.project_id == project_id)
        .order_by(db.ProjectAlertEmail.created_at)
        .all()
    )


def create_alert_email(session: Session, project_id: UUID, email: str) -> db.ProjectAlertEmail:
    try:
        alert_email = db.ProjectAlertEmail(project_id=project_id, email=email)
        session.add(alert_email)
        session.commit()
        session.refresh(alert_email)
        return alert_email
    except IntegrityError as exc:
        session.rollback()
        if hasattr(exc.orig, "diag") and getattr(exc.orig.diag, "constraint_name", None) == "uq_project_alert_email":
            raise DuplicateAlertEmailError(email) from exc
        raise


def get_alert_email_by_id(session: Session, alert_email_id: UUID) -> db.ProjectAlertEmail | None:
    return session.query(db.ProjectAlertEmail).filter(db.ProjectAlertEmail.id == alert_email_id).first()


def delete_alert_email(session: Session, alert_email_id: UUID) -> bool:
    alert_email = get_alert_email_by_id(session, alert_email_id)
    if not alert_email:
        return False
    session.delete(alert_email)
    session.commit()
    return True
