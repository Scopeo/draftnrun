import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.job import Job
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ada_backend.database.models import CronEntrypoint, CronStatus
from ada_backend.database.setup_db import get_db_session, get_db_url
from ada_backend.repositories.cron_repository import (
    get_cron_runs_by_cron_id,
    insert_cron_run,
    update_cron_run,
)
from ada_backend.scheduler.sync_cron_jobs_with_scheduler import schedule_sync_job
from ada_backend.scheduler.utils import log_sync_job_status
from ada_backend.services.cron.registry import CRON_REGISTRY
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


SCHEDULER_POLL_INTERVAL_SECONDS = 3


# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None

# Shared TraceManager instance for all scheduler jobs
# Since APScheduler doesn't propagate context variables, we create a singleton
# that gets set in each job's context to avoid creating multiple TraceManagers
_scheduler_trace_manager: Optional[TraceManager] = None


def initialize_scheduler_trace_manager() -> TraceManager:
    """Initialize the shared TraceManager singleton for scheduler jobs.

    This should be called once during scheduler startup (in run_scheduler()).

    Returns:
        The initialized TraceManager instance.
    """
    global _scheduler_trace_manager
    if _scheduler_trace_manager is None:
        _scheduler_trace_manager = TraceManager(project_name="ada-backend-scheduler")
    return _scheduler_trace_manager


def _get_scheduler_trace_manager() -> TraceManager:
    """Get the shared TraceManager for scheduler jobs.

    Raises:
        RuntimeError: If the TraceManager singleton has not been initialized.
    """
    if _scheduler_trace_manager is None:
        raise RuntimeError(
            "Scheduler TraceManager not initialized. "
            "Ensure initialize_scheduler_trace_manager() is called in run_scheduler() before jobs execute."
        )
    return _scheduler_trace_manager


def get_scheduler() -> AsyncIOScheduler:
    """Get the global scheduler instance."""
    if _scheduler is None:
        raise RuntimeError("Scheduler not initialized. Call start_scheduler() first.")
    return _scheduler


def _update_recent_run_status(session, cron_id: UUID, status: CronStatus, error: Optional[str] = None):
    """Set latest RUNNING cron run to given status and finalize timestamps."""
    recent_runs = get_cron_runs_by_cron_id(session, cron_id, limit=1)
    if recent_runs and recent_runs[0].status == CronStatus.RUNNING:
        update_cron_run(
            session=session,
            run_id=recent_runs[0].id,
            status=status,
            finished_at=datetime.now(timezone.utc),
            error=error,
        )


def _job_listener(event: JobExecutionEvent):
    """Log run completion in our database."""
    job_id = event.job_id

    log_sync_job_status(job_id, event)

    try:
        cron_id = UUID(job_id)
    except ValueError:
        LOGGER.warning(f"Skipping job with non-UUID id: {job_id}")
        return

    with get_db_session() as session:
        try:
            if event.exception:
                error_msg = str(event.exception)
                LOGGER.error(f"Cron job {cron_id} failed: {error_msg}")
                _update_recent_run_status(session, cron_id, CronStatus.ERROR, error_msg)
            else:
                LOGGER.info(f"Cron job {cron_id} completed successfully")
                _update_recent_run_status(session, cron_id, CronStatus.COMPLETED)
        except Exception as e:
            LOGGER.error(f"Error updating cron run for job {cron_id}: {e}")
            _update_recent_run_status(session, cron_id, CronStatus.ERROR, str(e))


async def _execute_cron_job(cron_id: UUID, entrypoint: CronEntrypoint, payload: Dict[str, Any]):
    """Execute a cron job by calling the appropriate entrypoint function.
    Also updates the cron run status in the database.

    """
    trace_manager = _get_scheduler_trace_manager()
    set_trace_manager(trace_manager)

    scheduled_time = datetime.now(timezone.utc)

    with get_db_session() as session:
        cron_run = insert_cron_run(
            session=session,
            cron_id=cron_id,
            scheduled_for=scheduled_time,
            started_at=scheduled_time,
            status=CronStatus.RUNNING,
        )
        run_id = cron_run.id

    try:
        LOGGER.info(f"Executing cron job {cron_id} with entrypoint {entrypoint}")

        if entrypoint not in CRON_REGISTRY:
            raise ValueError(f"Invalid entrypoint '{entrypoint}'.")

        spec = CRON_REGISTRY[entrypoint]

        # JSON from DB -> Parse to Execution Pydantic Model
        execution_payload = spec.execution_payload_model(**payload)

        with get_db_session() as session:
            # Execution Pydantic Model -> Execution Validator
            spec.execution_validator(execution_payload, db=session, cron_id=cron_id)

            # Execution Pydantic Model -> Executor
            result = await spec.executor(execution_payload, db=session, cron_id=cron_id)

        with get_db_session() as session:
            update_cron_run(
                session=session,
                run_id=run_id,
                status=CronStatus.COMPLETED,
                finished_at=datetime.now(timezone.utc),
                result=result,
            )

        LOGGER.info(f"Cron job {cron_id} executed successfully")
        return result

    except Exception as e:
        LOGGER.error(f"Cron job {cron_id} failed: {e}")
        with get_db_session() as session:
            update_cron_run(
                session=session,
                run_id=run_id,
                status=CronStatus.ERROR,
                finished_at=datetime.now(timezone.utc),
                error=str(e),
            )
        raise


def start_scheduler():
    """Initialize and start the APScheduler."""
    global _scheduler

    if _scheduler is not None:
        LOGGER.warning("Scheduler already running")
        return

    try:
        db_url = get_db_url()

        jobstore = SQLAlchemyJobStore(
            url=db_url,
            tablename="apscheduler_jobs",
            tableschema="scheduler",
        )

        job_defaults = {
            "coalesce": True,  # Combine multiple missed runs into one
            "misfire_grace_time": 300,  # Skip runs that are more than 5 minutes late
            "max_instances": 1,  # Only one instance of each job at a time
        }

        # Create scheduler
        _scheduler = AsyncIOScheduler(
            jobstores={"default": jobstore},
            executors={"default": AsyncIOExecutor()},
            job_defaults=job_defaults,
            timezone="UTC",
            jobstore_poll_interval=SCHEDULER_POLL_INTERVAL_SECONDS,
        )

        _scheduler.start()
        _scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        schedule_sync_job()
        LOGGER.info("APScheduler started with job execution enabled")

    except Exception as e:
        LOGGER.error(f"Failed to start scheduler: {e}")
        raise


def stop_scheduler():
    """Stop the APScheduler gracefully."""
    global _scheduler

    if _scheduler is None:
        LOGGER.warning("Scheduler not running")
        return

    try:
        _scheduler.shutdown(wait=True)
        _scheduler = None
        LOGGER.info("APScheduler stopped successfully")
    except Exception as e:
        LOGGER.error(f"Error stopping scheduler: {e}")


def add_job_to_scheduler(
    cron_id: UUID,
    cron_expr: str,
    tz: str,
    entrypoint: CronEntrypoint,
    payload: Dict[str, Any],
) -> Job:
    """Add a job to APScheduler."""
    scheduler = get_scheduler()

    # Parse cron expression
    # APScheduler expects: second, minute, hour, day, month, day_of_week
    # Standard cron is: minute, hour, day, month, day_of_week
    # So we need to prepend "0" for seconds
    if len(cron_expr.split()) == 5:
        cron_expr = f"0 {cron_expr}"

    job = scheduler.add_job(
        func=_execute_cron_job,
        trigger="cron",
        args=[cron_id, entrypoint, payload],
        id=str(cron_id),
        timezone=tz,
        **dict(zip(["second", "minute", "hour", "day", "month", "day_of_week"], cron_expr.split(), strict=False)),
        replace_existing=True,
    )

    if not scheduler.running:
        LOGGER.info(
            f"Added cron job {cron_id} to scheduler but scheduler not running "
            "job is not persisted to database. Check that your separate scheduler process is running."
        )
    else:
        LOGGER.info(f"Added cron job {cron_id} to scheduler with expression '{cron_expr}' in timezone '{tz}'")

    return job


def remove_job_from_scheduler(cron_id: UUID) -> bool:
    """
    Remove a job from APScheduler.
    Returns True if job was removed, False if not found
    """
    scheduler = get_scheduler()

    if not scheduler.running:
        LOGGER.info(
            f"Removed cron job {cron_id} from scheduler but scheduler not running "
            "The job will be removed from database with your next reconciliation."
        )
        return False

    try:
        scheduler.remove_job(str(cron_id))
        LOGGER.info(f"Removed cron job {cron_id} from scheduler")
        return True
    except Exception as e:
        LOGGER.warning(f"Could not remove job {cron_id} from scheduler: {e}")
        return False


def pause_job_in_scheduler(cron_id: UUID) -> bool:
    """
    Pause a job in APScheduler.
    Returns True if job was paused, False if not found
    """
    scheduler = get_scheduler()

    if not scheduler.running:
        LOGGER.info(
            f"Paused cron job {cron_id} in scheduler but scheduler not running "
            "The job will be paused in database with your next reconciliation."
        )
        return False

    try:
        scheduler.pause_job(str(cron_id))
        LOGGER.info(f"Paused cron job {cron_id} in scheduler")
        return True
    except Exception as e:
        LOGGER.warning(f"Could not pause job {cron_id} in scheduler: {e}")
        return False


def resume_job_in_scheduler(cron_id: UUID) -> bool:
    """
    Resume a job in APScheduler.
    Returns True if job was resumed, False if not found
    """
    scheduler = get_scheduler()

    if not scheduler.running:
        LOGGER.info(
            f"Resumed cron job {cron_id} in scheduler but scheduler not running "
            "The job will be resumed in database with your next reconciliation."
        )
        return False

    try:
        scheduler.resume_job(str(cron_id))
        LOGGER.info(f"Resumed cron job {cron_id} in scheduler")
        return True
    except Exception as e:
        LOGGER.warning(f"Could not resume job {cron_id} in scheduler: {e}")
        return False
