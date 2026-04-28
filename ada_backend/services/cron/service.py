import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import pytz
from croniter import croniter
from sqlalchemy.orm import Session

from ada_backend.context import CronExecutionContext, set_cron_execution_context
from ada_backend.database.models import CronJob, CronStatus
from ada_backend.mixpanel_analytics import track_cron_job_created, track_cron_job_deleted, track_cron_job_toggled
from ada_backend.repositories.cron_repository import (
    delete_cron_job,
    get_cron_job,
    get_cron_jobs_by_organization,
    get_cron_jobs_by_project_id,
    get_cron_runs_by_cron_id,
    insert_cron_job,
    insert_cron_run,
    permanently_delete_cron_jobs_by_ids,
    update_cron_job,
)
from ada_backend.scheduler.service import remove_job_from_scheduler
from ada_backend.schemas.cron_schema import (
    CronEntrypoint,
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
from ada_backend.services.cron.constants import CRON_MIN_INTERVAL_MINUTES
from ada_backend.services.cron.errors import (
    CronJobAccessDenied,
    CronJobNotFound,
    CronValidationError,
)
from ada_backend.services.cron.execution import run_cron_spec
from ada_backend.services.cron.registry import CRON_REGISTRY

LOGGER = logging.getLogger(__name__)


def _validate_cron_expression(cron_expr: str):
    """Validate cron expression format."""
    try:
        croniter(cron_expr)
    except (ValueError, TypeError) as e:
        raise CronValidationError(f"Invalid cron expression '{cron_expr}': {e}") from e


def _validate_timezone(tz: str):
    """Validate IANA timezone string."""
    try:
        pytz.timezone(tz)
    except pytz.exceptions.UnknownTimeZoneError:
        raise CronValidationError(f"Invalid timezone '{tz}'. Must be a valid IANA timezone.") from None


def _validate_maximum_frequency(cron_expr: str, min_interval_minutes: int = CRON_MIN_INTERVAL_MINUTES):
    """Validate that the cron expression doesn't exceed the maximum frequency limit."""
    try:
        base_time = datetime.now()
        cron = croniter(cron_expr, base_time)
        occurrences = [cron.get_next(datetime) for _ in range(10)]

        for i in range(len(occurrences) - 1):
            interval = occurrences[i + 1] - occurrences[i]
            if interval < timedelta(minutes=min_interval_minutes):
                raise CronValidationError(
                    f"Cron expression '{cron_expr}' runs too frequently. "
                    f"Minimum allowed interval is {min_interval_minutes} minutes, "
                    f"but found interval of {interval.total_seconds() / 60:.1f} minutes."
                )
    except CronValidationError:
        raise
    except Exception as e:
        raise CronValidationError(f"Error validating cron frequency: {e}") from e


def _assert_cron_in_org(session: Session, cron_id: UUID, organization_id: UUID) -> CronJob:
    """Ensure the cron job exists and belongs to the given organization."""
    cron_job = get_cron_job(session, cron_id)
    if not cron_job:
        raise CronJobNotFound(cron_id)
    if cron_job.organization_id != organization_id:
        raise CronJobAccessDenied(cron_id, organization_id)
    return cron_job


def _validate_and_enrich_payload_for_entrypoint(
    entrypoint: CronEntrypoint,
    payload: dict[str, Any],
    session: Session,
    organization_id: UUID,
    cron_id: UUID,
    **kwargs,
) -> Any:
    """Validate user payload and produce persisted execution payload."""
    if entrypoint not in CRON_REGISTRY:
        available = ", ".join(e.value for e in CRON_REGISTRY.keys())
        raise CronValidationError(f"Invalid entrypoint '{entrypoint}'. Available: {available}")

    spec = CRON_REGISTRY[entrypoint]

    try:
        # Raw dict -> User Pydantic Model
        user_input = spec.user_payload_model(**payload)

        # User Pydantic Model -> Registration Validator -> Execution Pydantic Model
        execution_model = spec.registration_validator(
            user_input=user_input,
            db=session,
            organization_id=organization_id,
            cron_id=cron_id,
            **kwargs,
        )

        return execution_model

    except Exception as e:
        raise CronValidationError(f"Invalid payload for entrypoint '{entrypoint}': {e}") from e


def _run_post_registration_hook(
    entrypoint: CronEntrypoint,
    execution_model: Any,
    cron_id: UUID,
    session: Session,
    **kwargs,
) -> None:
    """Call the spec's post_registration_hook if it exists."""
    spec = CRON_REGISTRY.get(entrypoint)
    if not spec or not spec.post_registration_hook:
        return

    spec.post_registration_hook(
        execution_payload=execution_model,
        cron_id=cron_id,
        db=session,
        **kwargs,
    )


def get_cron_jobs_for_organization(
    session: Session,
    organization_id: UUID,
    enabled_only: bool = False,
) -> CronJobListResponse:
    """Get all cron jobs for an organization."""
    cron_jobs = get_cron_jobs_by_organization(session, organization_id, enabled_only)
    return CronJobListResponse(
        cron_jobs=[CronJobResponse.model_validate(job) for job in cron_jobs],
        total=len(cron_jobs),
    )


def get_cron_job_detail(
    session: Session,
    cron_id: UUID,
    include_runs: bool = False,
    organization_id: Optional[UUID] = None,
) -> CronJobWithRuns:
    """Return cron details; enforce org ownership if organization_id is provided."""
    cron_job = get_cron_job(session, cron_id)
    if not cron_job:
        raise CronJobNotFound(cron_id)

    if organization_id is not None and cron_job.organization_id != organization_id:
        raise CronJobAccessDenied(cron_id, organization_id)

    if include_runs:
        runs = get_cron_runs_by_cron_id(session, cron_id, limit=10)
        return CronJobWithRuns(
            **CronJobResponse.model_validate(cron_job).model_dump(),
            recent_runs=runs,
        )
    else:
        return CronJobWithRuns(**CronJobResponse.model_validate(cron_job).model_dump())


def create_cron_job(
    session: Session,
    organization_id: UUID,
    cron_data: CronJobCreate,
    **kwargs,  # For user_id, etc.
) -> CronJobResponse:
    """Create a cron job in the database."""
    _validate_cron_expression(cron_data.cron_expr)
    _validate_timezone(cron_data.tz)
    _validate_maximum_frequency(cron_data.cron_expr)

    # Generate cron_id early so it can be passed to registration validator
    cron_id = uuid.uuid4()

    execution_model = _validate_and_enrich_payload_for_entrypoint(
        entrypoint=cron_data.entrypoint,
        payload=cron_data.payload,
        session=session,
        organization_id=organization_id,
        cron_id=cron_id,
        **kwargs,
    )

    cron_job = insert_cron_job(
        session=session,
        cron_id=cron_id,
        organization_id=organization_id,
        name=cron_data.name,
        cron_expr=cron_data.cron_expr,
        tz=cron_data.tz,
        entrypoint=cron_data.entrypoint,
        payload=execution_model.model_dump(mode="json"),
        is_enabled=True,
    )

    LOGGER.info(f"Created cron job {cron_id}.")

    _run_post_registration_hook(
        entrypoint=cron_data.entrypoint,
        execution_model=execution_model,
        cron_id=cron_id,
        session=session,
        **kwargs,
    )

    user_id = kwargs.get("user_id")
    if user_id:
        track_cron_job_created(user_id, organization_id, entrypoint=cron_data.entrypoint)

    return CronJobResponse.model_validate(cron_job)


def update_cron_job_service(
    session: Session,
    cron_id: UUID,
    cron_data: CronJobUpdate,
    organization_id: UUID,
    **kwargs,  # For user_id, etc.
) -> CronJobResponse:
    """Update cron job fields in the database."""
    existing_cron = _assert_cron_in_org(session, cron_id, organization_id)

    if cron_data.cron_expr is not None:
        _validate_cron_expression(cron_data.cron_expr)
        _validate_maximum_frequency(cron_data.cron_expr)
    if cron_data.tz is not None:
        _validate_timezone(cron_data.tz)

    payload_to_store = None
    if cron_data.payload is not None:
        entrypoint = cron_data.entrypoint or existing_cron.entrypoint
        execution_model = _validate_and_enrich_payload_for_entrypoint(
            entrypoint=entrypoint,
            payload=cron_data.payload,
            session=session,
            organization_id=organization_id,
            cron_id=cron_id,
            **kwargs,
        )
        payload_to_store = execution_model.model_dump(mode="json")

    updated_cron = update_cron_job(
        session=session,
        cron_id=cron_id,
        name=cron_data.name,
        cron_expr=cron_data.cron_expr,
        tz=cron_data.tz,
        entrypoint=cron_data.entrypoint,
        payload=payload_to_store,
        is_enabled=cron_data.is_enabled,
    )

    if not updated_cron:
        raise CronJobNotFound(cron_id)

    LOGGER.info(f"Updated cron job {cron_id}.")

    return CronJobResponse.model_validate(updated_cron)


def delete_cron_job_service(
    session: Session,
    cron_id: UUID,
    organization_id: UUID,
    user_id: UUID | None = None,
) -> CronJobDeleteResponse:
    _assert_cron_in_org(session, cron_id, organization_id)

    success = delete_cron_job(session, cron_id)

    if success:
        LOGGER.info(f"Deleted cron job {cron_id}.")
        if user_id:
            track_cron_job_deleted(user_id, organization_id)
        return CronJobDeleteResponse(id=cron_id)

    raise CronJobNotFound(cron_id)


def permanently_delete_cron_jobs_by_project_service(session: Session, project_id: UUID) -> None:
    cron_jobs = get_cron_jobs_by_project_id(session, project_id)
    if not cron_jobs:
        return
    for cron_job in cron_jobs:
        try:
            remove_job_from_scheduler(cron_job.id)
            LOGGER.debug(f"Removed cron job {cron_job.id} from scheduler")
        except Exception as e:
            LOGGER.warning(f"Failed to remove cron job {cron_job.id} from scheduler: {e}")

    cron_job_ids = [cron_job.id for cron_job in cron_jobs]
    deleted_cron_jobs = permanently_delete_cron_jobs_by_ids(session, cron_job_ids)

    if deleted_cron_jobs > 0:
        LOGGER.info(f"Deleted {deleted_cron_jobs} cron jobs for project {project_id}")


def pause_cron_job(
    session: Session,
    cron_id: UUID,
    organization_id: UUID,
    user_id: UUID | None = None,
) -> CronJobPauseResponse:
    _assert_cron_in_org(session, cron_id, organization_id)
    updated_cron = update_cron_job(session, cron_id, is_enabled=False)
    if not updated_cron:
        raise CronJobNotFound(cron_id)

    if user_id:
        track_cron_job_toggled(user_id, organization_id, enabled=False)

    return CronJobPauseResponse(
        id=cron_id,
        is_enabled=False,
        message="Cron job paused successfully.",
    )


def resume_cron_job(
    session: Session,
    cron_id: UUID,
    organization_id: UUID,
    user_id: UUID | None = None,
) -> CronJobPauseResponse:
    _assert_cron_in_org(session, cron_id, organization_id)
    updated_cron = update_cron_job(session, cron_id, is_enabled=True)
    if not updated_cron:
        raise CronJobNotFound(cron_id)

    if user_id:
        track_cron_job_toggled(user_id, organization_id, enabled=True)

    return CronJobPauseResponse(
        id=cron_id,
        is_enabled=True,
        message="Cron job resumed successfully.",
    )


def get_cron_runs(
    session: Session,
    cron_id: UUID,
    organization_id: UUID,
) -> CronRunListResponse:
    """Return execution runs for a cron job (latest first)."""
    _assert_cron_in_org(session, cron_id, organization_id)
    runs = get_cron_runs_by_cron_id(session, cron_id)

    return CronRunListResponse(
        runs=runs,
        total=len(runs),
    )


def trigger_cron_job_now(
    session: Session,
    cron_id: UUID,
    organization_id: UUID,
) -> tuple[CronJobTriggerResponse, CronEntrypoint, dict[str, Any]]:
    """Validate the cron job and create a CronRun record to be executed in the background.

    Returns the trigger response alongside the entrypoint and payload needed to execute the run.
    """
    cron_job = _assert_cron_in_org(session, cron_id, organization_id)

    now = datetime.now(timezone.utc)
    cron_run = insert_cron_run(
        session=session,
        cron_id=cron_id,
        scheduled_for=now,
        started_at=now,
        status=CronStatus.RUNNING,
    )

    response = CronJobTriggerResponse(
        run_id=cron_run.id,
        cron_id=cron_id,
    )
    return response, cron_job.entrypoint, dict(cron_job.payload)


async def execute_cron_run(run_id: UUID, cron_id: UUID, entrypoint: CronEntrypoint, payload: dict[str, Any]) -> None:
    """Execute a manually triggered cron job run. Delegates to shared execution logic."""
    set_cron_execution_context(CronExecutionContext(run_id=run_id, cron_id=cron_id))
    try:
        await run_cron_spec(run_id=run_id, cron_id=cron_id, entrypoint=entrypoint, payload=payload)
    except Exception:
        LOGGER.exception("Manual cron run failed: run_id=%s cron_id=%s entrypoint=%s", run_id, cron_id, entrypoint)
