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
    get_user_from_supabase_token,
    user_has_access_to_organization_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.components_schema import ComponentFieldsOptionsResponse, ComponentsResponse
from ada_backend.services.category_service import get_all_categories_service
from ada_backend.services.components_service import (
    delete_component_service,
    get_all_components_endpoint,
    get_all_components_global_endpoint,
)

router = APIRouter(prefix="/components", tags=["Components"])
LOGGER = logging.getLogger(__name__)


def _get_all_components_with_error_handling(
    session: Session, release_stage: Optional[ReleaseStage], log_context: str, use_global: bool = False
):
    if use_global:
        return get_all_components_global_endpoint(session, release_stage)
    else:
        return get_all_components_endpoint(session, release_stage)


@router.get("/fields/options", response_model=ComponentFieldsOptionsResponse)
async def get_component_fields_options(
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    """Get available options for component fields (release stages, categories). All authenticated users."""
    return ComponentFieldsOptionsResponse(
        release_stages=[stage.value for stage in ReleaseStage],
        categories=get_all_categories_service(session),
    )


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
    delete_component_service(session, component_id)
    return None
