import logging
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ada_backend.routers.auth_router import get_user_from_supabase_token
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.trace_schema import RootTraceSpan, TraceSpan
from ada_backend.services.trace_service import get_root_traces_by_project, get_span_trace_service

LOGGER = logging.getLogger(__name__)


router = APIRouter(prefix="/traces")


# TODO: filter trace by graph_runner_id
@router.get("/project/{project_id}", response_model=List[RootTraceSpan], tags=["Metrics"])
async def get_root_traces(
    project_id: UUID,
    duration: int,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
) -> List[RootTraceSpan]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        response = get_root_traces_by_project(user.id, project_id, duration)
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.get("/{trace_id}/tree", response_model=TraceSpan, tags=["Metrics"])
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
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
