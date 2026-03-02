import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import UserRights, user_has_access_to_project_dependency
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.run_schema import RunCreateSchema, RunResponseSchema, RunUpdateStatusSchema
from ada_backend.services.errors import ProjectNotFound, RunNotFound
from ada_backend.services.run_service import create_run, get_run, update_run_status

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
    try:
        return create_run(
            session,
            project_id=project_id,
            input_payload=body.input_payload,
            trigger=body.trigger,
        )
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
    except Exception as e:
        LOGGER.exception("Failed to update run %s", run_id)
        raise HTTPException(status_code=500, detail="Internal server error") from e
