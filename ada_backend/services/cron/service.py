import logging
import uuid
from typing import Optional, Any
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from croniter import croniter
import pytz

from ada_backend.database.models import CronJob
from ada_backend.repositories.cron_repository import (
    get_cron_job,
    get_cron_jobs_by_organization,
    get_cron_runs_by_cron_id,
    insert_cron_job,
    update_cron_job,
    delete_cron_job,
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
    CronEntrypoint,
)
from ada_backend.scheduler.service import (
    add_job_to_scheduler,
    remove_job_from_scheduler,
    pause_job_in_scheduler,
    resume_job_in_scheduler,
)
from ada_backend.services.cron.registry import CRON_REGISTRY
from ada_backend.services.cron.errors import (
    CronValidationError,
    CronJobNotFound,
    CronJobAccessDenied,
    CronSchedulerError,
)
from ada_backend.services.cron.constants import CRON_MIN_INTERVAL_MINUTES

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
    **kwargs,
) -> dict[str, Any]:
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
            **kwargs,
        )

        # Execution Pydantic Model -> Store as JSON (dict)
        return execution_model.model_dump(mode="json")

    except Exception as e:
        raise CronValidationError(f"Invalid payload for entrypoint '{entrypoint}': {e}") from e


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
    """Create a cron job and schedule it."""
    _validate_cron_expression(cron_data.cron_expr)
    _validate_timezone(cron_data.tz)
    _validate_maximum_frequency(cron_data.cron_expr)

    execution_payload = _validate_and_enrich_payload_for_entrypoint(
        entrypoint=cron_data.entrypoint,
        payload=cron_data.payload,
        session=session,
        organization_id=organization_id,
        **kwargs,
    )

    cron_id = uuid.uuid4()

    cron_job = insert_cron_job(
        session=session,
        cron_id=cron_id,
        organization_id=organization_id,
        name=cron_data.name,
        cron_expr=cron_data.cron_expr,
        tz=cron_data.tz,
        entrypoint=cron_data.entrypoint,
        payload=execution_payload,
        is_enabled=True,
    )

    try:
        add_job_to_scheduler(
            cron_id=cron_id,
            cron_expr=cron_data.cron_expr,
            tz=cron_data.tz,
            entrypoint=cron_data.entrypoint,
            payload=execution_payload,
        )
        LOGGER.info(f"Created and scheduled cron job {cron_id}")
    except Exception as e:
        LOGGER.error(f"Failed to schedule cron job {cron_id}: {e}")
        update_cron_job(session, cron_id, is_enabled=False)
        raise CronSchedulerError(f"Failed to schedule cron job: {e}") from e

    return CronJobResponse.model_validate(cron_job)


def update_cron_job_service(
    session: Session,
    cron_id: UUID,
    cron_data: CronJobUpdate,
    organization_id: UUID,
    **kwargs,  # For user_id, etc.
) -> Optional[CronJobResponse]:
    """Update cron fields and reconcile scheduler if needed."""
    existing_cron = _assert_cron_in_org(session, cron_id, organization_id)

    if cron_data.cron_expr is not None:
        _validate_cron_expression(cron_data.cron_expr)
        _validate_maximum_frequency(cron_data.cron_expr)
    if cron_data.tz is not None:
        _validate_timezone(cron_data.tz)

    payload_to_store = None
    if cron_data.payload is not None:
        entrypoint = cron_data.entrypoint or existing_cron.entrypoint
        payload_to_store = _validate_and_enrich_payload_for_entrypoint(
            entrypoint=entrypoint,
            payload=cron_data.payload,
            session=session,
            organization_id=organization_id,
            **kwargs,
        )

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

    # Update scheduler if job parameters changed
    if any(
        [
            cron_data.cron_expr is not None,
            cron_data.tz is not None,
            cron_data.entrypoint is not None,
            cron_data.payload is not None,
        ]
    ):
        try:
            remove_job_from_scheduler(cron_id)
            if updated_cron.is_enabled:
                add_job_to_scheduler(
                    cron_id=cron_id,
                    cron_expr=updated_cron.cron_expr,
                    tz=updated_cron.tz,
                    entrypoint=updated_cron.entrypoint,
                    payload=updated_cron.payload,
                )
            LOGGER.info(f"Updated cron job {cron_id} in scheduler")
        except Exception as e:
            LOGGER.error(f"Failed to update cron job {cron_id} in scheduler: {e}")
            # Don't fail the whole operation, just log the error

    # Handle pause/resume
    elif cron_data.is_enabled is not None:
        if cron_data.is_enabled and not existing_cron.is_enabled:
            resume_job_in_scheduler(cron_id)
        elif not cron_data.is_enabled and existing_cron.is_enabled:
            pause_job_in_scheduler(cron_id)

    return CronJobResponse.model_validate(updated_cron)


def delete_cron_job_service(
    session: Session,
    cron_id: UUID,
    organization_id: UUID,
) -> Optional[CronJobDeleteResponse]:
    """
    Delete a cron job after asserting org ownership.
    First removes the job from the scheduler, then deletes the job from the database.
    """
    _assert_cron_in_org(session, cron_id, organization_id)

    remove_job_from_scheduler(cron_id)
    success = delete_cron_job(session, cron_id)

    if success:
        LOGGER.info(f"Deleted cron job {cron_id}")
        return CronJobDeleteResponse(id=cron_id)

    return None


def pause_cron_job(session: Session, cron_id: UUID, organization_id: UUID) -> Optional[CronJobPauseResponse]:
    """Set cron job to inactive and pause scheduler job."""
    _assert_cron_in_org(session, cron_id, organization_id)
    updated_cron = update_cron_job(session, cron_id, is_enabled=False)
    if not updated_cron:
        return None

    pause_job_in_scheduler(cron_id)

    return CronJobPauseResponse(
        id=cron_id,
        is_enabled=False,
        message="Cron job paused successfully",
    )


def resume_cron_job(session: Session, cron_id: UUID, organization_id: UUID) -> Optional[CronJobPauseResponse]:
    """Set cron job to active and resume scheduler job."""
    _assert_cron_in_org(session, cron_id, organization_id)
    updated_cron = update_cron_job(session, cron_id, is_enabled=True)
    if not updated_cron:
        return None

    resume_job_in_scheduler(cron_id)

    return CronJobPauseResponse(
        id=cron_id,
        is_enabled=True,
        message="Cron job resumed successfully",
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


def sync_project_cron_jobs(
    session: Session,
    project_id: UUID,
    user_id: str,
) -> dict[str, Any]:
    """
    Sync cron jobs from project's Start node configuration.

    This function:
    1. Finds all Start nodes in the project's draft graph
    2. Extracts cron configuration from Start node parameters
    3. Creates/updates/deletes cron jobs in the scheduler accordingly

    Returns a dict with sync status and created/updated/deleted job IDs.
    """
    from ada_backend.repositories.project_repository import get_project_with_details
    from ada_backend.repositories.graph_runner_repository import get_component_nodes
    from ada_backend.repositories.component_repository import get_component_instance_by_id
    from ada_backend.database.models import EnvType

    project = get_project_with_details(session, project_id)
    if not project:
        raise CronValidationError(f"Project {project_id} not found")

    organization_id = project.organization_id

    # Get draft graph runner
    draft_graph_runner = next((gr for gr in project.graph_runners if gr.env == EnvType.DRAFT), None)
    if not draft_graph_runner:
        return {
            "status": "no_draft_graph",
            "message": "No draft graph found for project",
            "created": [],
            "updated": [],
            "deleted": [],
        }

    # Get all component nodes in the graph
    component_nodes = get_component_nodes(session, draft_graph_runner.graph_runner_id)

    # Find Start nodes (nodes with is_start_node=True)
    start_nodes = [node for node in component_nodes if node.is_start_node]

    if not start_nodes:
        return {
            "status": "no_start_nodes",
            "message": "No start nodes found in draft graph",
            "created": [],
            "updated": [],
            "deleted": [],
        }

    created_jobs = []
    updated_jobs = []
    errors = []

    for start_node in start_nodes:
        component_instance = get_component_instance_by_id(session, start_node.component_instance_id)
        if not component_instance:
            continue

        # Extract cron parameters from basic_parameters (list of BasicParameter objects)
        cron_enabled = False
        cron_expression = None
        cron_timezone = "UTC"
        payload_schema_value = None

        # Iterate through the list of basic parameters
        for param in component_instance.basic_parameters:
            param_name = param.parameter_definition.name
            param_value = param.value

            if param_name == "cron_enabled":
                # Convert string to boolean
                cron_enabled = param_value.lower() == "true" if param_value else False
            elif param_name == "cron_expression":
                cron_expression = param_value
            elif param_name == "cron_timezone":
                cron_timezone = param_value if param_value else "UTC"
            elif param_name == "payload_schema":
                payload_schema_value = param_value

        # Extract default payload from the payload_schema
        import json

        cron_payload = {}
        if payload_schema_value:
            try:
                schema = json.loads(payload_schema_value)
                if isinstance(schema, dict) and "default" in schema:
                    cron_payload = schema["default"]
                elif isinstance(schema, dict) and "properties" in schema:
                    cron_payload = {}
                    for prop_name, prop_schema in schema["properties"].items():
                        if isinstance(prop_schema, dict) and "default" in prop_schema:
                            cron_payload[prop_name] = prop_schema["default"]
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                LOGGER.warning(
                    f"Failed to extract default from payload_schema for component {component_instance.id}: {e}"
                )
                cron_payload = {}

        # Check if a cron job already exists for this project+env
        existing_jobs = get_cron_jobs_by_organization(session, organization_id, enabled_only=False)
        existing_job = None
        for job in existing_jobs:
            job_payload = job.payload or {}
            if job_payload.get("project_id") == str(project_id) and job_payload.get("env") == "draft":
                existing_job = job
                break

        if cron_enabled and cron_expression:
            # Create or update cron job
            job_name = f"{project.project_name} - Draft (Auto-scheduled)"
            payload_data = {
                "project_id": str(project_id),
                "env": "draft",
                "input_data": cron_payload,
            }

            try:
                if existing_job:
                    # Update existing job
                    cron_data = CronJobUpdate(
                        name=job_name,
                        cron_expr=cron_expression,
                        tz=cron_timezone,
                        payload=payload_data,
                        is_enabled=True,
                    )
                    updated_job = update_cron_job_service(
                        session,
                        existing_job.id,
                        cron_data,
                        organization_id,
                        user_id=user_id,
                    )
                    updated_jobs.append(str(updated_job.id))
                    LOGGER.info(f"Updated cron job {updated_job.id} for project {project_id}")
                else:
                    # Create new job
                    cron_data = CronJobCreate(
                        name=job_name,
                        cron_expr=cron_expression,
                        tz=cron_timezone,
                        entrypoint=CronEntrypoint.AGENT_INFERENCE,
                        payload=payload_data,
                    )
                    created_job = create_cron_job(
                        session,
                        organization_id,
                        cron_data,
                        user_id=user_id,
                    )
                    created_jobs.append(str(created_job.id))
                    LOGGER.info(f"Created cron job {created_job.id} for project {project_id}")
            except Exception as e:
                error_msg = f"Failed to sync cron job for project {project_id}: {str(e)}"
                LOGGER.error(error_msg)
                errors.append(error_msg)
        elif existing_job:
            # Cron disabled but job exists - pause it
            try:
                pause_cron_job(session, existing_job.id, organization_id)
                updated_jobs.append(str(existing_job.id))
                LOGGER.info(f"Paused cron job {existing_job.id} for project {project_id}")
            except Exception as e:
                error_msg = f"Failed to pause cron job {existing_job.id}: {str(e)}"
                LOGGER.error(error_msg)
                errors.append(error_msg)

    return {
        "status": "success" if not errors else "partial_success",
        "message": f"Synced cron jobs for project {project_id}",
        "created": created_jobs,
        "updated": updated_jobs,
        "deleted": [],
        "errors": errors if errors else None,
    }
