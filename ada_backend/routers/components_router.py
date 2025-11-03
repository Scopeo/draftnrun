from typing import Annotated, Optional
import logging
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
from ada_backend.services.components_service import (
    get_all_components_endpoint,
    delete_component_service,
)
from ada_backend.services.errors import EntityInUseDeletionError
from ada_backend.services.user_roles_service import is_user_super_admin
from ada_backend.routers.auth_router import get_user_from_supabase_token

router = APIRouter(prefix="/components", tags=["Components"])
LOGGER = logging.getLogger(__name__)


def _ensure_user_has_id(user: SupabaseUser) -> None:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")


def _get_all_components_with_error_handling(session: Session, release_stage: Optional[ReleaseStage], log_context: str):
    try:
        return get_all_components_endpoint(session, release_stage)
    except Exception as e:
        LOGGER.error(f"Failed to get components {log_context}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{organization_id}", response_model=ComponentsResponse)
def get_all_components(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value)),
    ],
    release_stage: Optional[ReleaseStage] = None,
    session: Session = Depends(get_db),
):
    _ensure_user_has_id(user)
    return _get_all_components_with_error_handling(
        session,
        release_stage,
        f"for organization {organization_id} (release_stage={release_stage})",
    )


@router.get("/", response_model=ComponentsResponse)
async def get_all_components_global(
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    release_stage: Optional[ReleaseStage] = None,
    session: Session = Depends(get_db),
):
    """Return all components regardless of organization. Super admin only."""
    _ensure_user_has_id(user)
    is_super = await is_user_super_admin(user)
    if not is_super:
        raise HTTPException(status_code=403, detail="Access denied")
    return _get_all_components_with_error_handling(
        session,
        release_stage,
        f"(global) by super admin (release_stage={release_stage})",
    )


@router.delete("/{component_id}", status_code=204)
async def delete_component(
    component_id: UUID,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    """Delete a component definition. Super admin only."""
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        is_super = await is_user_super_admin(user)
        if not is_super:
            raise HTTPException(status_code=403, detail="Access denied")
        delete_component_service(session, component_id)
        return None
    except HTTPException:
        raise
    except EntityInUseDeletionError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete {e.entity_type}: it is currently used by {e.instance_count} instance(s)",
        ) from e
    except Exception as e:
        LOGGER.error(f"Failed to delete component {component_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
