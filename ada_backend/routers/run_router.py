import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import UserRights, user_has_access_to_project_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.project_schema import ChatResponse
from ada_backend.schemas.run_schema import (
    AsyncRunAcceptedSchema,
    RunCreateSchema,
    RunListPagination,
    RunListResponse,
    RunResponseSchema,
    RunRetrySchema,
    RunUpdateStatusSchema,
)
from ada_backend.services.errors import (
    InvalidRunStatusTransition,
    ProjectNotFound,
    ResultsBucketNotConfigured,
    RunNotFound,
    RunResultNotFound,
)
from ada_backend.services.run_service import (
    create_run,
    get_run,
    get_run_result,
    get_runs,
    retry_run,
    update_run_status,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["Runs"])


@router.get(
    "/{project_id}/runs",
    response_model=RunListResponse,
)
def list_runs_endpoint(
    project_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=100, description="Number of runs per page"),
) -> RunListResponse:
    """List runs for a project, newest first, with pagination."""
    try:
        runs, total = get_runs(session, project_id=project_id, page=page, page_size=page_size)
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return RunListResponse(
            runs=runs,
            pagination=RunListPagination(
                page=page,
                page_size=page_size,
                total_items=total,
                total_pages=total_pages,
            ),
        )
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception("Failed to list runs for project %s", project_id)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
    try:
        return create_run(session, project_id=project_id, trigger=body.trigger)
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception("Failed to create run for project %s", project_id)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
    try:
        return get_run(session, run_id=run_id, project_id=project_id)
    except RunNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception("Failed to get run %s", run_id)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
    except (RunNotFound, RunResultNotFound) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ResultsBucketNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception("Failed to get result for run %s", run_id)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
    try:
        return update_run_status(
            session,
            run_id=run_id,
            project_id=project_id,
            status=body.status,
            error=body.error,
            trace_id=body.trace_id,
        )
    except RunNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidRunStatusTransition as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception("Failed to update run %s", run_id)
        raise HTTPException(status_code=500, detail="Internal server error") from e


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
    except Exception as exc:
        LOGGER.error("Failed to retry run %s for project %s", run_id, project_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error while retrying run") from exc
