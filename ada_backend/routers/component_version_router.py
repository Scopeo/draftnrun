from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import ensure_super_admin_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.components_schema import UpdateComponentFieldsRequest
from ada_backend.services.component_version_service import (
    delete_component_version_service,
    update_component_fields_service,
)

router = APIRouter(prefix="/components", tags=["Components"])


@router.put("/{component_id}/versions/{component_version_id}/fields")
async def update_component_fields(
    component_id: UUID,
    component_version_id: UUID,
    payload: UpdateComponentFieldsRequest,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
):
    """Update component fields (categories, is_agent, function_callable, release_stage). Super admin only."""
    update_component_fields_service(
        session,
        component_id,
        component_version_id,
        is_agent=payload.is_agent,
        function_callable=payload.function_callable,
        category_ids=payload.category_ids,
        release_stage=payload.release_stage,
    )
    return {"status": "ok"}


@router.delete("/{component_id}/versions/{component_version_id}", status_code=204)
async def delete_component_version(
    component_id: UUID,
    component_version_id: UUID,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
):
    """Delete a specific component version. Super admin only."""
    delete_component_version_service(session, component_id, component_version_id)
    return
