import logging
from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, RunStatus
from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import UserRights, user_has_access_to_organization_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.chart_schema import ChartsResponse
from ada_backend.schemas.monitor_schema import KPISResponse
from ada_backend.schemas.run_schema import OrgRunListResponse, RunListPagination
from ada_backend.services.charts_service import get_charts_by_projects
from ada_backend.services.errors import RunNotFound
from ada_backend.services.metrics.monitor_kpis_service import get_monitoring_kpis_by_projects
from ada_backend.services.run_service import get_org_run_input, get_org_runs

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


@router.get("/org/{organization_id}/runs", response_model=OrgRunListResponse, tags=["Runs"])
def list_organization_runs(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    statuses: List[RunStatus] = Query(None),
    project_ids: List[UUID] = Query(None),
    trigger: Optional[CallType] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> OrgRunListResponse:
    try:
        runs, total = get_org_runs(
            session,
            organization_id=organization_id,
            page=page,
            page_size=page_size,
            statuses=statuses,
            project_ids=project_ids,
            trigger=trigger,
            date_from=date_from,
            date_to=date_to,
        )
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return OrgRunListResponse(
            runs=runs,
            pagination=RunListPagination(
                page=page,
                page_size=page_size,
                total_items=total,
                total_pages=total_pages,
            ),
        )
    except Exception as e:
        LOGGER.error("Failed to list runs for organization %s", organization_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/org/{organization_id}/runs/{run_id}/input", tags=["Runs"])
def get_organization_run_input(
    organization_id: UUID,
    run_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> dict:
    try:
        input_data = get_org_run_input(session, run_id=run_id, organization_id=organization_id)
        if input_data is None:
            raise HTTPException(status_code=404, detail=f"Input not found for run {run_id}")
        return input_data
    except RunNotFound:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found in organization {organization_id}")
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error("Failed to get input for run %s in organization %s", run_id, organization_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
