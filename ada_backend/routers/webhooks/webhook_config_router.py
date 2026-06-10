from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import UserRights, user_has_access_to_project_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.webhook_schema import TypeformWebhookCreateRequest, TypeformWebhookCreateResponse
from ada_backend.services.webhooks.typeform_setup_service import create_typeform_webhook_service

router = APIRouter(prefix="/projects/{project_id}/webhooks", tags=["Webhooks"])


@router.post("/typeform", response_model=TypeformWebhookCreateResponse, status_code=201)
def create_typeform_webhook(
    project_id: UUID,
    body: TypeformWebhookCreateRequest,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
) -> TypeformWebhookCreateResponse:
    return create_typeform_webhook_service(
        session=session,
        project_id=project_id,
        events=body.events,
        filter_options=body.filter_options,
        rotate_secret=body.rotate_secret,
    )
