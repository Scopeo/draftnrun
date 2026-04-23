from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    UserRights,
    user_has_access_to_organization_dependency,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.cron_schema import (
    CronJobCreate,
    CronJobDeleteResponse,
    CronJobListResponse,
    CronJobPauseResponse,
    CronJobResponse,
    CronJobTriggerResponse,
    CronJobUpdate,
    CronJobWithRuns,
    CronRunListResponse,
)
from ada_backend.services.cron.service import (
    create_cron_job,
    delete_cron_job_service,
    execute_cron_run,
    get_cron_job_detail,
    get_cron_jobs_for_organization,
    get_cron_runs,
    pause_cron_job,
    resume_cron_job,
    trigger_cron_job_now,
    update_cron_job_service,
)

router = APIRouter(prefix="/organizations", tags=["Cron Jobs"])


@router.get("/{organization_id}/crons", response_model=CronJobListResponse)
def get_organization_cron_jobs(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    enabled_only: bool = Query(False, description="Return only enabled cron jobs"),
):
    """
    Get all cron jobs for an organization.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    return get_cron_jobs_for_organization(session, organization_id, enabled_only)


@router.get("/{organization_id}/crons/{cron_id}", response_model=CronJobWithRuns)
def get_cron_job_details(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
    include_runs: bool = Query(True, description="Include recent execution runs"),
):
    """
    Get detailed information about a specific cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    cron_job = get_cron_job_detail(session, cron_id, include_runs, organization_id=organization_id)
    return cron_job


@router.post("/{organization_id}/crons", response_model=CronJobResponse, status_code=201)
def create_organization_cron_job(
    organization_id: UUID,
    cron_data: CronJobCreate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Create a new cron job for an organization.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    return create_cron_job(session, organization_id, cron_data, user_id=user.id)


@router.patch("/{organization_id}/crons/{cron_id}", response_model=CronJobResponse)
def update_organization_cron_job(
    organization_id: UUID,
    cron_id: UUID,
    cron_data: CronJobUpdate,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Update an existing cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    updated_cron = update_cron_job_service(session, cron_id, cron_data, organization_id, user_id=user.id)
    return updated_cron


@router.delete("/{organization_id}/crons/{cron_id}", response_model=CronJobDeleteResponse)
def delete_organization_cron_job(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Delete a cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    result = delete_cron_job_service(session, cron_id, organization_id, user_id=user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Cron job not found")

    return result


@router.post("/{organization_id}/crons/{cron_id}/pause", response_model=CronJobPauseResponse)
def pause_organization_cron_job(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Pause a cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    result = pause_cron_job(session, cron_id, organization_id=organization_id, user_id=user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Cron job not found")

    return result


@router.post("/{organization_id}/crons/{cron_id}/resume", response_model=CronJobPauseResponse)
def resume_organization_cron_job(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.DEVELOPER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Resume a paused cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    result = resume_cron_job(session, cron_id, organization_id=organization_id, user_id=user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Cron job not found")

    return result


@router.get("/{organization_id}/crons/{cron_id}/runs", response_model=CronRunListResponse)
def get_cron_job_runs(
    organization_id: UUID,
    cron_id: UUID,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Get execution history for a cron job.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    result = get_cron_runs(session, cron_id, organization_id=organization_id)
    if not result:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return result


@router.post("/{organization_id}/crons/{cron_id}/trigger", response_model=CronJobTriggerResponse, status_code=202)
def trigger_organization_cron_job(
    organization_id: UUID,
    cron_id: UUID,
    background_tasks: BackgroundTasks,
    user: Annotated[
        SupabaseUser,
        Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.MEMBER.value)),
    ],
    session: Session = Depends(get_db),
):
    """
    Manually trigger a cron job to run immediately.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    result, entrypoint, payload = trigger_cron_job_now(session, cron_id, organization_id=organization_id)
    background_tasks.add_task(
        execute_cron_run,
        run_id=result.run_id,
        cron_id=cron_id,
        entrypoint=entrypoint,
        payload=payload,
    )
    return result
