import logging
from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.models import CallType, RunStatus
from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_dependency,
    user_has_access_to_project_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.run_schema import (
    AsyncRunAcceptedSchema,
    OrgRunListResponse,
    RunCreateSchema,
    RunListPagination,
    RunResponseSchema,
    RunRetrySchema,
    RunUpdateStatusSchema,
)
from ada_backend.services.errors import RunNotFound
from ada_backend.services.run_service import (
    create_run,
    get_org_run_input,
    get_org_runs,
    get_run,
    get_run_result,
    retry_run,
    update_run_status,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Runs"])
@router.post(
    "/{project_id}/runs",
    response_model=RunResponseSchema,
    status_code=201,
)
def create_run_endpoint(
    project_id: UUID,
    body: RunCreateSchema,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> RunResponseSchema:
    """Create a new run for the project. Run starts with status pending."""
    return create_run(session, project_id=project_id, trigger=body.trigger)


@router.get(
    "/{project_id}/runs/{run_id}",
    response_model=RunResponseSchema,
)
def get_run_endpoint(
    project_id: UUID,
    run_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> RunResponseSchema:
    return get_run(session, run_id=run_id, project_id=project_id)


@router.get(
    "/{project_id}/runs/{run_id}/result",
    response_model=ChatResponse,
)
def get_run_result_endpoint(
    project_id: UUID,
    run_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> ChatResponse:
    """Return the run result (ChatResponse) from S3. Run must be completed and have a result_id."""
    try:
        return get_run_result(session, run_id=run_id, project_id=project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch(
    "/{project_id}/runs/{run_id}",
    response_model=RunResponseSchema,
)
def update_run_status_endpoint(
    project_id: UUID,
    run_id: UUID,
    body: RunUpdateStatusSchema,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> RunResponseSchema:
    """Update run status (and optionally error/trace_id). Run must belong to the given project."""
    return update_run_status(
        session,
        run_id=run_id,
        project_id=project_id,
        status=body.status,
        error=body.error,
        trace_id=body.trace_id,
    )


@router.post(
    "/{project_id}/runs/{run_id}/retry",
    response_model=AsyncRunAcceptedSchema,
    status_code=202,
)
def retry_run_endpoint(
    project_id: UUID,
    run_id: UUID,
    body: RunRetrySchema,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
) -> AsyncRunAcceptedSchema:
    try:
        return retry_run(
            session=session,
            run_id=run_id,
            project_id=project_id,
            env=body.env.value if body.env else None,
            graph_runner_id=body.graph_runner_id,
        )
    except RunNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found for project {project_id}") from exc
    except ValueError as exc:
        LOGGER.warning("Invalid retry request for run %s in project %s: %s", run_id, project_id, exc)
        raise HTTPException(
            status_code=400,
            detail="Invalid retry request. Provide env or graph_runner_id and ensure run input exists.",
        ) from exc


org_router = APIRouter(prefix="/org", tags=["Runs"])


@org_router.get("/{organization_id}/runs", response_model=OrgRunListResponse)
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


@org_router.get("/{organization_id}/runs/{run_id}/input")
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
