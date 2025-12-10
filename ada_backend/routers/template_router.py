from fastapi import APIRouter, Depends, HTTPException
import logging
from uuid import UUID

from sqlalchemy.orm import Session
from ada_backend.database.setup_db import get_db
from ada_backend.services.template_service import list_templates_services
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.template_schema import TemplateResponse


router = APIRouter(prefix="/templates", tags=["Templates"])
LOGGER = logging.getLogger(__name__)


@router.get("/{organization_id}", summary="Get Production Templates", tags=["Templates"])
def get_production_templates(
    organization_id: UUID,
    session: Session = Depends(get_db),
    user: SupabaseUser = Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
) -> list[TemplateResponse]:
    """
    Retrieve production templates for a given organization.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return list_templates_services(session)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception(
            "Failed to list templates for organization %s",
            organization_id,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
