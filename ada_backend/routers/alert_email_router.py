from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import UserRights, user_has_access_to_project_dependency
from ada_backend.schemas.alert_email_schema import AlertEmailCreate, AlertEmailResponse
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.services import alert_email_service

router = APIRouter(prefix="/projects/{project_id}/alert-emails", tags=["Alert Emails"])


@router.get("", response_model=List[AlertEmailResponse])
def list_alert_emails(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    return alert_email_service.list_alert_emails_by_project_service(session, project_id)


@router.post("", response_model=AlertEmailResponse, status_code=201)
def create_alert_email(
    project_id: UUID,
    body: AlertEmailCreate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    return alert_email_service.create_alert_email_service(session, project_id=project_id, email=body.email)


@router.delete("/{alert_email_id}", status_code=204)
def delete_alert_email(
    project_id: UUID,
    alert_email_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    alert_email_service.delete_alert_email_service(session, project_id, alert_email_id)
