from fastapi import APIRouter
from uuid import UUID
from typing import Annotated
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db

from ada_backend.services.tag_service import list_tag_versions_service

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import (
    user_has_access_to_project_dependency,
    UserRights,
)

router = APIRouter(prefix="/tags")


@router.get("/{project_id}", response_model=list[str], tags=["Tags"])
def list_tag_versions(
    project_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return list_tag_versions_service(session, project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
