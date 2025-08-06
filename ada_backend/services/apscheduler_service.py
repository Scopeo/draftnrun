"""
APScheduler service for managing job definitions in database.
Job execution is handled by a separate APScheduler process.
"""

import logging
from typing import Dict, Any
from uuid import UUID

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from ada_backend.database.models import ScheduledWorkflow
from ada_backend.services.schedule_executor import execute_celery_task
from settings import settings

LOGGER = logging.getLogger(__name__)


def _create_temp_scheduler() -> BackgroundScheduler:
    """Create temporary scheduler for job management operations"""
    jobstore = SQLAlchemyJobStore(
        url=settings.ADA_DB_URL,
        tablename="apscheduler_jobs",
        metadata=None,
    )

    return BackgroundScheduler(
        jobstores={"default": jobstore},
        executors={"default": ThreadPoolExecutor(20)},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        timezone="UTC",
    )


def sync_scheduled_workflow(scheduled_workflow: ScheduledWorkflow):
    """Sync a scheduled workflow to APScheduler database"""
    job_id = f"workflow_{scheduled_workflow.uuid}"

    # Create temporary scheduler just for this operation
    scheduler = _create_temp_scheduler()

    try:
        scheduler.start()

        if scheduled_workflow.enabled:
            trigger = CronTrigger.from_crontab(
                scheduled_workflow.cron_expression, timezone=scheduled_workflow.timezone or "UTC"
            )

            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)

            scheduler.add_job(
                func=execute_celery_task,
                trigger=trigger,
                id=job_id,
                args=[
                    str(scheduled_workflow.project_id) if scheduled_workflow.project_id else "",
                    str(scheduled_workflow.uuid),
                    scheduled_workflow.type.value,
                    scheduled_workflow.args,
                ],
                name=f"Workflow {scheduled_workflow.type.value} - {scheduled_workflow.uuid}",
                replace_existing=True,
            )

            LOGGER.info(f"Synced scheduled workflow {scheduled_workflow.uuid} to APScheduler database")
        else:
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)
                LOGGER.info(f"Removed disabled workflow {scheduled_workflow.uuid} from APScheduler database")

    finally:
        scheduler.shutdown()


def remove_scheduled_workflow(workflow_uuid: UUID):
    """Remove a scheduled workflow from APScheduler database"""
    job_id = f"workflow_{workflow_uuid}"

    # Create temporary scheduler just for this operation
    scheduler = _create_temp_scheduler()

    try:
        scheduler.start()
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            LOGGER.info(f"Removed workflow {workflow_uuid} from APScheduler database")
    finally:
        scheduler.shutdown()


def sync_all_workflows(session: Session) -> Dict[str, Any]:
    """Sync all enabled workflows to APScheduler database"""
    try:
        workflows = session.query(ScheduledWorkflow).filter(ScheduledWorkflow.enabled).all()

        results = {"total": len(workflows), "successful": 0, "failed": 0, "errors": []}

        for workflow in workflows:
            try:
                sync_scheduled_workflow(workflow)
                results["successful"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"workflow_id": workflow.id, "uuid": str(workflow.uuid), "error": str(e)})

        LOGGER.info(f"Synced {results['successful']}/{results['total']} workflows to APScheduler database")
        return results

    except Exception as e:
        LOGGER.error(f"Failed to sync workflows: {str(e)}")
        return {"total": 0, "successful": 0, "failed": 1, "errors": [{"error": str(e)}]}
