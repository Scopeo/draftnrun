import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

import pytz
from croniter import croniter
from sqlalchemy.orm import Session

from ada_backend.database.models import CronJob
from ada_backend.repositories.cron_repository import (
    delete_cron_job,
    get_cron_job,
    get_cron_jobs_by_organization,
    get_cron_runs_by_cron_id,
    insert_cron_job,
    update_cron_job,
)
from ada_backend.schemas.cron_schema import (
    CronEntrypoint,
    CronJobCreate,
    CronJobDeleteResponse,
    CronJobListResponse,
    CronJobPauseResponse,
    CronJobResponse,
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
        raise CronJobNotFound(f"Cron job {cron_id} not found")
    if cron_job.organization_id != organization_id:
        raise CronJobAccessDenied("Access denied")
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
        raise CronJobNotFound(f"Cron job {cron_id} not found")

    if organization_id is not None and cron_job.organization_id != organization_id:
        raise CronJobAccessDenied("Access denied")

    if include_runs:
        runs = get_cron_runs_by_cron_id(session, cron_id)
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

    return CronJobResponse.model_validate(cron_job)


def update_cron_job_service(
    session: Session,
    cron_id: UUID,
    cron_data: CronJobUpdate,
    organization_id: UUID,
    **kwargs,  # For user_id, etc.
) -> Optional[CronJobResponse]:
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
        raise CronJobNotFound(f"Cron job {cron_id} not found")

    LOGGER.info(f"Updated cron job {cron_id}.")

    return CronJobResponse.model_validate(updated_cron)


def delete_cron_job_service(
    session: Session,
    cron_id: UUID,
    organization_id: UUID,
) -> Optional[CronJobDeleteResponse]:
    """
    Delete a cron job from the database after asserting org ownership.
    """
    _assert_cron_in_org(session, cron_id, organization_id)

    success = delete_cron_job(session, cron_id)

    if success:
        LOGGER.info(f"Deleted cron job {cron_id}.")
        return CronJobDeleteResponse(id=cron_id)

    return None


def pause_cron_job(session: Session, cron_id: UUID, organization_id: UUID) -> Optional[CronJobPauseResponse]:
    """Set cron job to inactive in the database."""
    _assert_cron_in_org(session, cron_id, organization_id)
    updated_cron = update_cron_job(session, cron_id, is_enabled=False)
    if not updated_cron:
        return None

    return CronJobPauseResponse(
        id=cron_id,
        is_enabled=False,
        message="Cron job paused successfully.",
    )


def resume_cron_job(session: Session, cron_id: UUID, organization_id: UUID) -> Optional[CronJobPauseResponse]:
    """Set cron job to active in the database."""
    _assert_cron_in_org(session, cron_id, organization_id)
    updated_cron = update_cron_job(session, cron_id, is_enabled=True)
    if not updated_cron:
        return None

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
