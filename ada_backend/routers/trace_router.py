import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ada_backend.database.models import CallType, EnvType
from ada_backend.routers.auth_router import get_user_from_supabase_token
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.trace_schema import TraceSpan, PaginatedRootTracesResponse
from ada_backend.services.trace_service import (
    get_root_traces_by_project,
    get_span_trace_service,
)

LOGGER = logging.getLogger(__name__)


router = APIRouter()


@router.get("/projects/{project_id}/traces", response_model=PaginatedRootTracesResponse, tags=["Metrics"])
async def get_root_traces(
    project_id: UUID,
    duration: int,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    environment: Optional[EnvType] = None,
    call_type: Optional[CallType] = None,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=1000, description="Number of items per page"),
    graph_runner_id: Optional[UUID] = None,
) -> PaginatedRootTracesResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        response = get_root_traces_by_project(
            user.id,
            project_id,
            duration,
            environment,
            call_type,
            page,
            page_size,
            graph_runner_id,
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception(
            "Failed to get root traces for project %s (duration=%s, env=%s, call_type=%s)",
            project_id,
            duration,
            environment,
            call_type,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.get("/traces/{trace_id}/tree", response_model=TraceSpan, tags=["Metrics"])
async def get_span_trace(
    trace_id: str,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        response = get_span_trace_service(user.id, trace_id)
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception(
            "Failed to get span trace for trace_id=%s",
            trace_id,
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
