from typing import Annotated, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.components_schema import ComponentsResponse
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
)
from ada_backend.services.components_service import get_all_components_endpoint

router = APIRouter(prefix="/components", tags=["Components"])


@router.get("/{organization_id}", response_model=ComponentsResponse)
def get_all_components(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    release_stage: Optional[ReleaseStage] = None,
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_all_components_endpoint(session, release_stage)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
