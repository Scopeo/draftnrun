import logging
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    ensure_super_admin_dependency,
    super_admin_or_admin_api_key_dependency,
    user_has_access_to_organization_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.chart_schema import ChartsResponse
from ada_backend.schemas.credits_schema import (
    ComponentVersionCost,
    ComponentVersionCostResponse,
    OrganizationLimit,
    OrganizationLimitAndUsageResponse,
    OrganizationLimitResponse,
)
from ada_backend.services.charts_service import get_credit_usage_table_chart
from ada_backend.services.credits_service import (
    create_organization_limit_service,
    delete_component_version_cost_service,
    delete_organization_limit_service,
    get_all_organization_limits_and_usage_service,
    update_organization_limit_service,
    upsert_component_version_cost_service,
)
from ada_backend.services.errors import (
    ComponentVersionCostNotFound,
    OrganizationLimitNotFound,
)

router = APIRouter(tags=["Credits"])
LOGGER = logging.getLogger(__name__)


@router.get("/organizations-limits-and-usage", response_model=List[OrganizationLimitAndUsageResponse])
def get_all_organization_limits_and_usage_endpoint(
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
    month: int = Query(..., description="Month (1-12)"),
    year: int = Query(..., description="Year"),
) -> List[OrganizationLimitAndUsageResponse]:
    try:
        return get_all_organization_limits_and_usage_service(session, month, year)
    except Exception as e:
        LOGGER.error(f"Failed to get organization limits and usage: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/organizations/{organization_id}/organization-limits", response_model=OrganizationLimitResponse)
async def create_organization_limit_endpoint(
    organization_id: UUID,
    organization_limit_create: OrganizationLimit,
    verified_admin_api_key_or_super_admin: Annotated[None, Depends(super_admin_or_admin_api_key_dependency)],
    session: Session = Depends(get_db),
) -> OrganizationLimitResponse:
    try:
        return create_organization_limit_service(
            session,
            organization_id,
            organization_limit_create.limit,
        )
    except Exception as e:
        LOGGER.error(f"Failed to create organization limit: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch("/organizations/{organization_id}/organization-limits", response_model=OrganizationLimitResponse)
async def update_organization_limit_endpoint(
    id: UUID,
    organization_id: UUID,
    organization_limit: float,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
) -> OrganizationLimitResponse:
    try:
        return update_organization_limit_service(
            session,
            id=id,
            organization_id=organization_id,
            limit=organization_limit,
        )
    except OrganizationLimitNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to update organization limit: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/organizations/{organization_id}/organization-limits", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_limit_endpoint(
    id: UUID,
    organization_id: UUID,
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
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
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
) -> ComponentVersionCostResponse:
    try:
        return upsert_component_version_cost_service(
            session,
            component_version_id,
            component_version_cost_update.credits_per_call,
            component_version_cost_update.credits_per,
        )
    except ComponentVersionCostNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
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
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
) -> None:
    try:
        return delete_component_version_cost_service(session, component_version_id)
    except Exception as e:
        LOGGER.error(f"Failed to delete component version cost: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/organizations/{organization_id}/credit-usage", response_model=ChartsResponse)
async def get_organization_credit_usage_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> ChartsResponse:
    try:
        return await get_credit_usage_table_chart(session, organization_id)
    except Exception as e:
        LOGGER.error(f"Failed to get organization credit usage: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
