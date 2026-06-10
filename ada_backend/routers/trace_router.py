import logging
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, EnvType
from ada_backend.database.setup_db import get_db
from ada_backend.repositories.project_repository import get_project
from ada_backend.routers.auth_router import (
    UserRights,
    get_user_from_supabase_token,
    user_has_access_to_project_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.trace_schema import PaginatedRootTracesResponse, TraceSpan
from ada_backend.services.metrics.utils import query_trace_project_id
from ada_backend.services.trace_service import (
    get_root_traces_by_project,
    get_span_trace_service,
)
from ada_backend.services.user_roles_service import get_user_access_to_organization

LOGGER = logging.getLogger(__name__)


router = APIRouter()


@router.get("/projects/{project_id}/traces", response_model=PaginatedRootTracesResponse, tags=["Metrics"])
async def get_root_traces(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    duration: Optional[int] = Query(None, description="Lookback window in days (ignored when start_time is provided)"),
    environment: Optional[EnvType] = None,
    call_type: Optional[CallType] = None,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=1000, description="Number of items per page"),
    graph_runner_id: Optional[UUID] = None,
    search: Optional[str] = Query(
        None, min_length=1, max_length=500, description="Search traces by input message content"
    ),
    start_time: Optional[datetime] = Query(None, description="Start of date range filter (ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="End of date range filter (ISO 8601)"),
    session: Session = Depends(get_db),
) -> PaginatedRootTracesResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    if duration is None and start_time is None and end_time is None:
        raise HTTPException(
            status_code=400,
            detail="Either 'duration' or at least one of 'start_time'/'end_time' must be provided",
        )
    project = get_project(session, project_id)
    organization_id = project.organization_id if project else None
    try:
        response = get_root_traces_by_project(
            user.id,
            project_id,
            duration=duration,
            environment=environment,
            call_type=call_type,
            page=page,
            page_size=page_size,
            graph_runner_id=graph_runner_id,
            organization_id=organization_id,
            search=search,
            start_time=start_time,
            end_time=end_time,
        )
        return response
    except ValueError as e:
        LOGGER.warning("Invalid trace search parameters for project %s: %s", project_id, e)
        raise HTTPException(status_code=400, detail=f"Invalid parameters for trace search on project {project_id}")


@router.get("/traces/{trace_id}/tree", response_model=TraceSpan, tags=["Metrics"])
async def get_span_trace(
    trace_id: str,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    await _check_user_access_to_trace(user, trace_id, session)
    try:
        response = get_span_trace_service(user.id, trace_id)
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


async def _check_user_access_to_trace(user: SupabaseUser, trace_id: str, session: Session) -> None:
    """Verify the user belongs to the org owning the trace's project.

    The trace_id is not project-scoped in the URL, so tenancy must be resolved
    from the trace's spans before returning span contents.
    """
    project_id = query_trace_project_id(trace_id)
    if project_id is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    project = get_project(session, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Trace not found")
    try:
        access = await get_user_access_to_organization(user=user, organization_id=project.organization_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail="You don't have access to this trace") from e
    if access.role not in UserRights.MEMBER.value:
        raise HTTPException(status_code=403, detail="You don't have access to this trace")
