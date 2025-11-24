from fastapi import APIRouter
from typing import Annotated, List
from uuid import UUID
import logging
from sqlalchemy.orm import Session
from fastapi import Depends, status, HTTPException

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import UserRights, user_has_access_to_organization_dependency
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.credits_schema import (
    ComponentVersionCostResponse,
    ComponentVersionCost,
    OrganizationLimitResponse,
    OrganizationLimit,
)
from ada_backend.services.credits_service import (
    upsert_component_version_cost_service,
    create_organization_limit_service,
    update_organization_limit_service,
    delete_organization_limit_service,
    get_all_organization_limits_service,
    delete_component_version_cost_service,
)

router = APIRouter(tags=["Credits"])
LOGGER = logging.getLogger(__name__)


@router.get("/organizations-limits", response_model=List[OrganizationLimitResponse])
def get_all_organization_limits_endpoint(
    year: int,
    month: int,
    session: Session = Depends(get_db),
) -> List[OrganizationLimitResponse]:
    try:
        return get_all_organization_limits_service(session, year, month)
    except Exception as e:
        LOGGER.error(f"Failed to get organization limit: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/organizations/{organization_id}/organization-limits", response_model=OrganizationLimitResponse)
def create_organization_limit_endpoint(
    organization_id: UUID,
    organization_limit_create: OrganizationLimit,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> OrganizationLimitResponse:
    try:
        if not user.id:
            raise HTTPException(status_code=400, detail="User ID not found")
        return create_organization_limit_service(
            session,
            organization_id,
            organization_limit_create.year,
            organization_limit_create.month,
            organization_limit_create.limit,
        )
    except Exception as e:
        LOGGER.error(f"Failed to create organization limit: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch("/organizations/{organization_id}/organization-limits", response_model=OrganizationLimitResponse)
def update_organization_limit_endpoint(
    id: UUID,
    organization_id: UUID,
    organization_limit: float,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> OrganizationLimitResponse:
    try:
        return update_organization_limit_service(
            session,
            id=id,
            organization_id=organization_id,
            limit=organization_limit,
        )
    except Exception as e:
        LOGGER.error(f"Failed to update organization limit: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/organizations/{organization_id}/organization-limits", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization_limit_endpoint(
    id: UUID,
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    try:
        return delete_organization_limit_service(session, id, organization_id)
    except Exception as e:
        LOGGER.error(f"Failed to delete organization limit: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch(
    "/organizations/{organization_id}/component-version-costs/{component_version_id}",
    response_model=ComponentVersionCostResponse,
)
def upsert_component_version_cost_endpoint(
    organization_id: UUID,
    component_version_id: UUID,
    component_version_cost_update: ComponentVersionCost,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> ComponentVersionCostResponse:
    try:
        return upsert_component_version_cost_service(
            session,
            component_version_id,
            component_version_cost_update.credits_per_call,
            component_version_cost_update.credits_per_second,
            component_version_cost_update.credits_per_input_token,
            component_version_cost_update.credits_per_output_token,
        )
    except Exception as e:
        LOGGER.error(f"Failed to update component version cost: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete(
    "/organizations/{organization_id}/component-version-costs/{component_version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_component_version_cost_endpoint(
    organization_id: UUID,
    component_version_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    try:
        return delete_component_version_cost_service(session, component_version_id)
    except Exception as e:
        LOGGER.error(f"Failed to delete component version cost: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
