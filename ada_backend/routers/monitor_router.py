import logging
from datetime import datetime, timezone
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ada_backend.database.models import CallType
from ada_backend.routers.auth_router import UserRights, user_has_access_to_organization_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.chart_schema import ChartsResponse
from ada_backend.schemas.monitor_schema import KPISResponse, OrgTokenUsageResponse
from ada_backend.services.charts_service import get_charts_by_projects
from ada_backend.services.metrics.monitor_kpis_service import get_monitoring_kpis_by_projects, get_org_token_usage

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor")


def _parse_token_usage_filter(
    values: list[str] | None,
    *,
    field_name: str,
    default_values: list[int],
    minimum: int,
    maximum: int | None = None,
) -> list[int] | None:
    if values is None:
        return default_values

    normalized_values = [value.strip().lower() for value in values]
    if "all" in normalized_values:
        if len(normalized_values) > 1:
            raise HTTPException(status_code=400, detail=f"{field_name}=all cannot be combined with explicit values")
        return None

    parsed_values = []
    for value in normalized_values:
        try:
            parsed_value = int(value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{field_name} must contain integers or 'all'") from exc
        if parsed_value < minimum or (maximum is not None and parsed_value > maximum):
            range_detail = f"between {minimum} and {maximum}" if maximum is not None else f">= {minimum}"
            raise HTTPException(status_code=400, detail=f"{field_name} values must be {range_detail}")
        parsed_values.append(parsed_value)

    return sorted(set(parsed_values))


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


@router.get("/org/{organization_id}/token-usage", response_model=OrgTokenUsageResponse, tags=["Metrics"])
async def get_organization_token_usage(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    years: list[str] | None = Query(
        None,
        description="UTC years to include. Repeat for multiple values, or pass 'all'. Defaults to current year.",
    ),
    months: list[str] | None = Query(
        None,
        description=(
            "UTC months (1-12) to include. Repeat for multiple values, or pass 'all'. "
            "Defaults to current month."
        ),
    ),
    by_model: bool = True,
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    now = datetime.now(tz=timezone.utc)
    resolved_years = _parse_token_usage_filter(
        years,
        field_name="years",
        default_values=[now.year],
        minimum=1,
    )
    resolved_months = _parse_token_usage_filter(
        months,
        field_name="months",
        default_values=[now.month],
        minimum=1,
        maximum=12,
    )
    return get_org_token_usage(
        organization_id=organization_id,
        years=resolved_years,
        months=resolved_months,
        by_model=by_model,
    )
