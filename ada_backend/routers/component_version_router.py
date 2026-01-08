import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import ensure_super_admin_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.components_schema import UpdateComponentReleaseStageRequest
from ada_backend.services.component_version_service import (
    delete_component_version_service,
    update_component_version_release_stage_service,
)
from ada_backend.services.errors import (
    ComponentNotFound,
    ComponentVersionMismatchError,
    EntityInUseDeletionError,
)

router = APIRouter(prefix="/components", tags=["Components"])
LOGGER = logging.getLogger(__name__)


@router.put("/{component_id}/versions/{component_version_id}/release-stage")
async def update_component_release_stage(
    component_id: UUID,
    component_version_id: UUID,
    payload: UpdateComponentReleaseStageRequest,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
):
    """Update a component's release stage. Super admin only."""
    try:
        update_component_version_release_stage_service(
            session,
            component_id,
            component_version_id,
            payload.release_stage,
        )
        return {"status": "ok"}
    except ComponentNotFound as e:
        raise HTTPException(status_code=404, detail="Resource not found") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to update component {component_id} release stage to {payload.release_stage}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/{component_id}/versions/{component_version_id}", status_code=204)
async def delete_component_version(
    component_id: UUID,
    component_version_id: UUID,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
):
    """Delete a specific component version. Super admin only."""
    try:
        delete_component_version_service(session, component_id, component_version_id)
        return
    except EntityInUseDeletionError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete {e.entity_type}: it is currently used by {e.instance_count} instance(s)",
        ) from e
    except ComponentVersionMismatchError as e:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Component version {e.component_version_id} does not belong to component {e.expected_component_id}"
            ),
        ) from e
    except Exception as e:
        LOGGER.error(f"Failed to delete component version {component_version_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
