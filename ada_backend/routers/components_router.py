import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    ensure_super_admin_dependency,
    user_has_access_to_organization_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.components_schema import ComponentsResponse
from ada_backend.services.components_service import (
    delete_component_service,
    get_all_components_endpoint,
    get_all_components_global_endpoint,
)
from ada_backend.services.errors import EntityInUseDeletionError

router = APIRouter(prefix="/components", tags=["Components"])
LOGGER = logging.getLogger(__name__)


def _get_all_components_with_error_handling(
    session: Session, release_stage: Optional[ReleaseStage], log_context: str, use_global: bool = False
):
    try:
        if use_global:
            return get_all_components_global_endpoint(session, release_stage)
        else:
            return get_all_components_endpoint(session, release_stage)
    except Exception as e:
        LOGGER.error(f"Failed to get components {log_context}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{organization_id}", response_model=ComponentsResponse)
def get_all_components(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    release_stage: Optional[ReleaseStage] = None,
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    return _get_all_components_with_error_handling(
        session,
        release_stage,
        f"for organization {organization_id} (release_stage={release_stage})",
    )


@router.get("/", response_model=ComponentsResponse)
async def get_all_components_global(
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    release_stage: Optional[ReleaseStage] = None,
    session: Session = Depends(get_db),
):
    """Return all components regardless of organization. Super admin only."""
    return _get_all_components_with_error_handling(
        session,
        release_stage,
        f"(global) by super admin (release_stage={release_stage})",
        use_global=True,
    )


@router.delete("/{component_id}", status_code=204)
async def delete_component(
    component_id: UUID,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
):
    """Delete a component definition. Super admin only."""
    try:
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
