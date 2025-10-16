from typing import Annotated
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
)
from ada_backend.schemas.cron_schema import (
    CronJobCreate,
    CronJobUpdate,
    CronJobResponse,
    CronJobWithRuns,
    CronJobListResponse,
    CronRunListResponse,
    CronJobDeleteResponse,
    CronJobPauseResponse,
)
from ada_backend.services.cron.service import (
    get_cron_jobs_for_organization,
    get_cron_job_detail,
    create_cron_job,
    update_cron_job_service,
    delete_cron_job_service,
    pause_cron_job,
    resume_cron_job,
    get_cron_runs,
)
from ada_backend.services.cron.errors import (
    CronValidationError,
    CronJobNotFound,
    CronJobAccessDenied,
    CronSchedulerError,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/crons", tags=["Cron Jobs"])


@router.get("/{organization_id}", response_model=CronJobListResponse)
def get_organization_cron_jobs(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value)),
    ],
    session: Session = Depends(get_db),
    enabled_only: bool = Query(False, description="Return only enabled cron jobs"),
):
    """
    Get all cron jobs for an organization.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return get_cron_jobs_for_organization(session, organization_id, enabled_only)
    except Exception as e:
        LOGGER.error(f"Failed to fetch cron jobs for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{organization_id}/{cron_id}", response_model=CronJobWithRuns)
def get_cron_job_details(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value)),
    ],
    session: Session = Depends(get_db),
    include_runs: bool = Query(True, description="Include recent execution runs"),
):
    """
    Get detailed information about a specific cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        cron_job = get_cron_job_detail(session, cron_id, include_runs, organization_id=organization_id)
        return cron_job
    except CronJobNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except CronJobAccessDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to fetch cron job {cron_id} for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{organization_id}", response_model=CronJobResponse, status_code=201)
def create_organization_cron_job(
    organization_id: UUID,
    cron_data: CronJobCreate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Create a new cron job for an organization.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        return create_cron_job(session, organization_id, cron_data, user_id=user.id)
    except CronValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except CronSchedulerError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to create cron job for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch("/{organization_id}/{cron_id}", response_model=CronJobResponse)
def update_organization_cron_job(
    organization_id: UUID,
    cron_id: UUID,
    cron_data: CronJobUpdate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Update an existing cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        updated_cron = update_cron_job_service(session, cron_id, cron_data, organization_id, user_id=user.id)
        return updated_cron
    except CronJobNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except CronJobAccessDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except CronValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to update cron job {cron_id} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/{organization_id}/{cron_id}", response_model=CronJobDeleteResponse)
def delete_organization_cron_job(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Delete a cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        result = delete_cron_job_service(session, cron_id, organization_id)
        if not result:
            raise HTTPException(status_code=404, detail="Cron job not found")
        return result
    except CronJobNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except CronJobAccessDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to delete cron job {cron_id} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{organization_id}/{cron_id}/pause", response_model=CronJobPauseResponse)
def pause_organization_cron_job(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Pause a cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        result = pause_cron_job(session, cron_id, organization_id=organization_id)
        if not result:
            raise HTTPException(status_code=404, detail="Cron job not found")
        return result
    except CronJobNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except CronJobAccessDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to pause cron job {cron_id} for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/{organization_id}/{cron_id}/resume", response_model=CronJobPauseResponse)
def resume_organization_cron_job(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Resume a paused cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        result = resume_cron_job(session, cron_id, organization_id=organization_id)
        if not result:
            raise HTTPException(status_code=404, detail="Cron job not found")
        return result
    except CronJobNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except CronJobAccessDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to resume cron job {cron_id} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/{organization_id}/{cron_id}/runs", response_model=CronRunListResponse)
def get_cron_job_runs(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Get execution history for a cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        result = get_cron_runs(session, cron_id, organization_id=organization_id)
        if not result:
            raise HTTPException(status_code=404, detail="Cron job not found")
        return result
    except CronJobNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except CronJobAccessDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(
            f"Failed to fetch runs for cron job {cron_id} for organization {organization_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Internal server error") from e
