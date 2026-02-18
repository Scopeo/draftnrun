import logging
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ada_backend.database.models import CallType
from ada_backend.routers.auth_router import UserRights, user_has_access_to_organization_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.chart_schema import ChartsResponse
from ada_backend.schemas.monitor_schema import KPISResponse
from ada_backend.services.charts_service import get_charts_by_projects
from ada_backend.services.metrics.monitor_kpis_service import get_monitoring_kpis_by_projects

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor")


@router.get("/org/{organization_id}/charts", response_model=ChartsResponse, tags=["Metrics"])
async def get_organization_charts(
    organization_id: UUID,
    duration: int,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    project_ids: List[UUID] = Query(
        None,
        description="List of project IDs.",
    ),
    call_type: CallType | None = None,
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        response = await get_charts_by_projects(
            project_ids=project_ids,
            duration_days=duration,
            call_type=call_type,
        )
        return response
    except ValueError as e:
        LOGGER.error(
            f"Failed to get charts for organization {organization_id} with duration {duration}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get charts for organization {organization_id} with duration {duration}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/org/{organization_id}/kpis", response_model=KPISResponse, tags=["Metrics"])
async def get_organization_kpis(
    organization_id: UUID,
    duration: int,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    project_ids: List[UUID] = Query(
        None,
        description="List of project IDs.",
    ),
    call_type: CallType | None = None,
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        response = get_monitoring_kpis_by_projects(
            user_id=user.id,
            project_ids=project_ids,
            organization_id=organization_id,
            duration_days=duration,
            call_type=call_type,
        )
        return response
    except ValueError as e:
        LOGGER.error(
            f"Failed to get KPIs for organization {organization_id} with duration {duration}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Bad request") from e
    except Exception as e:
        LOGGER.error(
            f"Failed to get KPIs for organization {organization_id} with duration {duration}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e
