import asyncio
import logging
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.job import Job
from apscheduler.triggers.interval import IntervalTrigger

from ada_backend.database.setup_db import get_db_session, get_db_url
from ada_backend.database.models import CronStatus, CronEntrypoint
from ada_backend.repositories.cron_repository import (
    insert_cron_run,
    update_cron_run,
    get_all_enabled_cron_jobs,
    get_cron_runs_by_cron_id,
)
from ada_backend.services.cron.registry import CRON_REGISTRY
from engine.trace.trace_context import get_trace_manager, set_trace_manager
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


SCHEDULER_POLL_INTERVAL_SECONDS = 3
SYNC_CRON_JOBS_WITH_APSCHEDULER_INTERVAL_SECONDS = 30
ID_RECONCILE_CRON_JOBS = "00000000-0000-0000-0000-000000000007"


# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None

# Lock to prevent concurrent reconciliation runs
_reconciliation_lock: Optional[asyncio.Lock] = None


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

    try:
        cron_id = UUID(job_id)
    except ValueError:
        LOGGER.warning(f"Skipping job with non-UUID id: {job_id}")
        return

    # We track failures in logs for reconciliation job but don't create database entries due to foreign key constraint
    # on cron_runs table.
    if job_id == ID_RECONCILE_CRON_JOBS:
        if event.exception:
            error_msg = str(event.exception)
            LOGGER.error(f"Reconciliation job {cron_id} failed: {error_msg}", exc_info=event.exception)
        else:
            LOGGER.debug(f"Reconciliation job {cron_id} completed successfully")
        return

    with get_db_session() as session:
        try:
            if event.exception:
                error_msg = str(event.exception)
                LOGGER.error(f"Cron job {cron_id} failed: {error_msg}")
                _update_recent_run_status(session, cron_id, CronStatus.ERROR, error_msg)
            else:
                LOGGER.info(f"Cron job {cron_id} completed successfully")
                _update_recent_run_status(session, cron_id, CronStatus.SUCCESS)
        except Exception as e:
            LOGGER.error(f"Error updating cron run for job {cron_id}: {e}")
            _update_recent_run_status(session, cron_id, CronStatus.ERROR, str(e))


async def _execute_cron_job(cron_id: UUID, entrypoint: CronEntrypoint, payload: Dict[str, Any]):
    """Execute a cron job by calling the appropriate entrypoint function.
    Also updates the cron run status in the database.

    """
    # Ensure trace_manager is available in this job's execution context
    # APScheduler doesn't propagate context variables, so we need to set it here
    if get_trace_manager() is None:
        set_trace_manager(TraceManager(project_name="ada-backend-scheduler"))

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
                status=CronStatus.SUCCESS,
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


def start_scheduler(sync_and_execute_jobs: bool = False):
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

        if sync_and_execute_jobs:
            _scheduler.start()
            _scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
            LOGGER.info("APScheduler started with job execution enabled")
            _schedule_reconciliation_job()
        else:
            # TODO: Remove the raise exception when scheduler is not even implemented
            # Right now we keep it to have a short working PR but the logic is now that
            # the process launching with execute_jobs=True will handle both
            # the execution and the reconciliation of the jobs
            LOGGER.info("APScheduler initialized to avoid error in code execution")

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


def _schedule_reconciliation_job(interval_seconds: int = SYNC_CRON_JOBS_WITH_APSCHEDULER_INTERVAL_SECONDS):
    """
    Schedule or update the periodic reconciliation job.

    Args:
        interval_seconds: Interval in seconds between reconciliation runs
    """
    scheduler = get_scheduler()

    if not scheduler.running:
        LOGGER.warning("Cannot schedule reconciliation job - scheduler is not running")
        return

    try:
        existing_job = scheduler.get_job(ID_RECONCILE_CRON_JOBS)
        if existing_job:
            scheduler.reschedule_job(job_id=ID_RECONCILE_CRON_JOBS, trigger=IntervalTrigger(seconds=interval_seconds))
            LOGGER.info(f"Updated reconciliation job interval to {interval_seconds} seconds")
            return

        scheduler.add_job(
            func=_reconcile_and_load_jobs_async,
            trigger="interval",
            seconds=interval_seconds,
            id=ID_RECONCILE_CRON_JOBS,
            name="Reconcile cron jobs from database",
            replace_existing=True,
        )
        LOGGER.info(f"Scheduled periodic reconciliation every {interval_seconds} seconds")
    except Exception as e:
        LOGGER.error(f"Failed to schedule reconciliation job: {e}")
        raise


def _reconcile_and_load_jobs():
    """
    Reconciles jobs between the database and APScheduler, ensuring the database
    is the source of truth. It adds/updates jobs from the DB to the scheduler
    and removes jobs from the scheduler that are no longer active or present in the DB.
    """
    scheduler = get_scheduler()
    if not scheduler:
        LOGGER.warning("Attempted to reconcile jobs, but scheduler is not running.")
        return

    LOGGER.info("Reconciling cron jobs between database and scheduler...")

    try:
        with get_db_session() as session:
            # 1. Get all active jobs from our DB (the source of truth)
            active_db_crons = get_all_enabled_cron_jobs(session)
            active_db_cron_ids = {str(cron.id) for cron in active_db_crons}
            LOGGER.info(f"Found {len(active_db_crons)} active cron jobs in the database.")

            # 2. Get all jobs currently in the scheduler's job store
            scheduler_jobs = scheduler.get_jobs()
            scheduler_job_ids = {job.id for job in scheduler_jobs}
            LOGGER.info(f"Found {len(scheduler_jobs)} jobs in the scheduler job store.")

            # 3. Remove stale jobs from the scheduler
            # Exclude the reconciliation job itself from removal (it's not in cron_jobs table)
            jobs_to_remove = scheduler_job_ids - active_db_cron_ids - {ID_RECONCILE_CRON_JOBS}
            if jobs_to_remove:
                LOGGER.info(f"Found {len(jobs_to_remove)} stale jobs to remove from scheduler.")
                for job_id in jobs_to_remove:
                    try:
                        remove_job_from_scheduler(UUID(job_id))
                    except Exception as e:
                        LOGGER.error(f"Failed to remove stale job {job_id} from scheduler: {e}")

            # 4. Add or update jobs from our DB to the scheduler
            LOGGER.info("Adding/updating jobs from database to scheduler...")
            for cron_job in active_db_crons:
                try:
                    add_job_to_scheduler(
                        cron_id=cron_job.id,
                        cron_expr=cron_job.cron_expr,
                        tz=cron_job.tz,
                        entrypoint=cron_job.entrypoint,
                        payload=cron_job.payload,
                    )
                except Exception as e:
                    LOGGER.error(f"Failed to load cron job {cron_job.id}: {e}")

        LOGGER.info("Cron job reconciliation complete.")

    except Exception as e:
        LOGGER.error(f"An error occurred during cron job reconciliation: {e}")


async def _reconcile_and_load_jobs_async():
    """
    Async wrapper for reconciliation that runs the sync function in a thread pool executor.
    This prevents blocking the event loop, allowing other jobs to run concurrently.

    Uses a lock to ensure only one reconciliation runs at a time, preventing thread buildup
    if reconciliation takes longer than the interval.
    """
    global _reconciliation_lock

    if _reconciliation_lock is None:
        _reconciliation_lock = asyncio.Lock()

    async with _reconciliation_lock:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _reconcile_and_load_jobs)


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
        **dict(zip(["second", "minute", "hour", "day", "month", "day_of_week"], cron_expr.split())),
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
