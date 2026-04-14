from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories import alert_email_repository


def list_alert_emails_by_project_service(session: Session, project_id: UUID) -> list[db.ProjectAlertEmail]:
    return alert_email_repository.list_alert_emails_by_project(session, project_id)


def create_alert_email_service(session: Session, project_id: UUID, email: str) -> db.ProjectAlertEmail:
    try:
        return alert_email_repository.create_alert_email(session, project_id=project_id, email=email)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"Email {email} is already configured for this project")


def delete_alert_email_service(session: Session, project_id: UUID, alert_email_id: UUID) -> None:
    alert_email = alert_email_repository.get_alert_email_by_id(session, alert_email_id)
    if not alert_email or alert_email.project_id != project_id:
        raise HTTPException(status_code=404, detail="Alert email not found")
    alert_email_repository.delete_alert_email(session, alert_email_id)
