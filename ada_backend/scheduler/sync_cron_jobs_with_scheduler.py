"""
This module handles the synchronization of cron jobs from the database to APScheduler.

The backend API (gunicorn service) writes cron job definitions to the database, and this module
safely imports those jobs into APScheduler. It runs a periodic sync job that:
- Reads all enabled cron jobs from the database (source of truth)
- Adds/updates jobs in APScheduler to match the database
- Removes jobs from APScheduler that are no longer in the database or are disabled

This ensures the scheduler always reflects the current state of cron jobs in the database.
"""

import asyncio
import logging
from typing import Optional
from uuid import UUID

from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import JobExecutionEvent

from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.cron_repository import get_all_enabled_cron_jobs

LOGGER = logging.getLogger(__name__)

SYNC_CRON_JOBS_WITH_APSCHEDULER_INTERVAL_SECONDS = 30
ID_SYSTEM_SYNC_CRON_JOBS = "00000000-0000-0000-0000-000000000007"

# Lock to prevent concurrent sync runs
_sync_lock: Optional[asyncio.Lock] = None


def schedule_sync_job(interval_seconds: int = SYNC_CRON_JOBS_WITH_APSCHEDULER_INTERVAL_SECONDS):
    """
    Schedule or update the periodic sync job.

    Args:
        interval_seconds: Interval in seconds between sync runs
    """
    from ada_backend.scheduler.service import get_scheduler

    scheduler = get_scheduler()

    if not scheduler.running:
        LOGGER.warning("Cannot schedule sync job - scheduler is not running")
        return

    try:
        existing_job = scheduler.get_job(ID_SYSTEM_SYNC_CRON_JOBS)
        if existing_job:
            scheduler.reschedule_job(
                job_id=ID_SYSTEM_SYNC_CRON_JOBS, trigger=IntervalTrigger(seconds=interval_seconds)
            )
            LOGGER.info(f"Updated sync job interval to {interval_seconds} seconds")
            return

        scheduler.add_job(
            func=_sync_and_load_jobs_async,
            trigger="interval",
            seconds=interval_seconds,
            id=ID_SYSTEM_SYNC_CRON_JOBS,
            name="Sync cron jobs from database",
            replace_existing=True,
        )
        LOGGER.info(f"Scheduled periodic sync every {interval_seconds} seconds")
    except Exception as e:
        LOGGER.error(f"Failed to schedule sync job: {e}")
        raise


def log_sync_job_status(job_id: str, event: JobExecutionEvent):
    """Log the status of the sync job execution.
    We track failures in logs for cron jobs but not for the system jobs.
    """
    if job_id == ID_SYSTEM_SYNC_CRON_JOBS:
        if event.exception:
            error_msg = str(event.exception)
            LOGGER.error(f"Reconciliation job {job_id} failed: {error_msg}", exc_info=event.exception)
        else:
            LOGGER.debug(f"Reconciliation job {job_id} completed successfully")
    return


def _sync_and_load_jobs():
    """
    Syncs jobs between the database and APScheduler, ensuring the database
    is the source of truth. It adds/updates jobs from the DB to the scheduler
    and removes jobs from the scheduler that are no longer active or present in the DB.
    """
    from ada_backend.scheduler.service import (
        get_scheduler,
        add_job_to_scheduler,
        remove_job_from_scheduler,
    )

    scheduler = get_scheduler()
    if not scheduler:
        LOGGER.warning("Attempted to sync jobs, but scheduler is not running.")
        return

    LOGGER.info("Syncing cron jobs between database and scheduler...")

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
            # Exclude the sync job itself from removal (it's not in cron_jobs table)
            jobs_to_remove = scheduler_job_ids - active_db_cron_ids - {ID_SYSTEM_SYNC_CRON_JOBS}
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

        LOGGER.info("Cron job sync complete.")

    except Exception as e:
        LOGGER.error(f"An error occurred during cron job sync: {e}")


async def _sync_and_load_jobs_async():
    """
    Async wrapper for sync that runs the sync function in a thread pool executor.
    This prevents blocking the event loop, allowing other jobs to run concurrently.

    Uses a lock to ensure only one sync runs at a time, preventing thread buildup
    if sync takes longer than the interval.
    """
    global _sync_lock

    if _sync_lock is None:
        _sync_lock = asyncio.Lock()

    async with _sync_lock:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_and_load_jobs)
