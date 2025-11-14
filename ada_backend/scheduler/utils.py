import logging
from apscheduler.events import JobExecutionEvent

LOGGER = logging.getLogger(__name__)

# System job ID for the sync job between cron table and apscheduler table
ID_SYSTEM_SYNC_CRON_JOBS = "00000000-0000-0000-0000-000000000007"


def log_sync_job_status(job_id: str, event: JobExecutionEvent):
    """Log the status of the sync job execution.

    We track failures in logs for cron jobs but not for the system jobs.
    This function is called from the job listener to handle logging for
    the system sync job separately from regular cron jobs.

    Args:
        job_id: The ID of the job that was executed
        event: The job execution event from APScheduler
    """
    if job_id == ID_SYSTEM_SYNC_CRON_JOBS:
        if event.exception:
            error_msg = str(event.exception)
            LOGGER.error(f"Reconciliation job {job_id} failed: {error_msg}", exc_info=event.exception)
        else:
            LOGGER.debug(f"Reconciliation job {job_id} completed successfully")
    return
