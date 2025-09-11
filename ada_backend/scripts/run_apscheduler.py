#!/usr/bin/env python3
"""
APScheduler daemon process for executing scheduled jobs.
This runs separately from the FastAPI app and handles all cron-based workflow scheduling.
"""

import sys
import signal
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED

from ada_backend.services.schedule_executor import execute_celery_task
from settings import settings

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)


def create_scheduler():
    """Create and configure the APScheduler instance"""

    # Database jobstore for workflow jobs
    db_jobstore = SQLAlchemyJobStore(
        url=settings.ADA_DB_URL,
        tablename="apscheduler_jobs",
        metadata=None,
    )

    # Memory jobstore for sync job only
    memory_jobstore = MemoryJobStore()

    # Create blocking scheduler (runs in main thread)
    scheduler = BlockingScheduler(
        jobstores={"default": db_jobstore, "memory": memory_jobstore},  # Workflow jobs go here  # Sync job goes here
        executors={"default": ThreadPoolExecutor(20)},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        timezone="UTC",
    )

    # Add event listeners for debugging
    def job_listener(event):
        """Log job execution events"""
        from datetime import datetime

        timestamp = datetime.now().isoformat()

        if event.exception:
            LOGGER.error(f"❌ Job {event.job_id} FAILED at {timestamp}")
            LOGGER.error(f"   ⚠️  Exception: {event.exception}")
        else:
            LOGGER.info(f"✅ Job {event.job_id} EXECUTED at {timestamp}")
            if "workflow_" in event.job_id:
                workflow_uuid = event.job_id.replace("workflow_", "")
                LOGGER.info(f"   🔄 Workflow UUID: {workflow_uuid}")

    def job_missed_listener(event):
        """Log missed job events"""
        from datetime import datetime

        timestamp = datetime.now().isoformat()
        LOGGER.warning(f"⏰ Job {event.job_id} MISSED at {timestamp}")
        LOGGER.warning(f"   📅 Scheduled time: {event.scheduled_run_time}")
        if "workflow_" in event.job_id:
            workflow_uuid = event.job_id.replace("workflow_", "")
            LOGGER.warning(f"   🔄 Workflow UUID: {workflow_uuid}")

    # Add listeners
    scheduler.add_listener(job_listener, mask=EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.add_listener(job_missed_listener, mask=EVENT_JOB_MISSED)

    return scheduler


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    LOGGER.info(f"Received signal {signum}, shutting down APScheduler...")
    sys.exit(0)


def sync_jobs_with_database(scheduler):
    """Dynamically sync scheduler jobs with database state"""
    try:
        import psycopg2
        from apscheduler.triggers.cron import CronTrigger

        # Get current jobs from scheduler (excluding our sync job)
        current_jobs = {job.id: job for job in scheduler.get_jobs() if job.id != "job_sync"}

        # Get jobs from database
        conn = psycopg2.connect(settings.ADA_DB_URL)
        cursor = conn.cursor()

        # Query scheduled_workflows to find all enabled workflows
        cursor.execute(
            """
            SELECT
                'workflow_' || sw.uuid::text as job_id,
                sw.uuid,
                sw.project_id,
                sw.type,
                sw.args,
                sw.cron_expression,
                sw.timezone,
                sw.enabled
            FROM scheduled_workflows sw
            WHERE sw.enabled = true
        """
        )

        db_jobs = cursor.fetchall()
        cursor.close()
        conn.close()

        db_job_ids = set()

        # Process each job from database
        for row in db_jobs:
            job_id, workflow_uuid, project_id, job_type, args, cron_expr, timezone, enabled = row
            db_job_ids.add(job_id)

            if job_id in current_jobs:
                # Job exists - check if it needs updating
                LOGGER.debug(f"🔍 Job {job_id} exists in scheduler")
            else:
                # New job - add it to scheduler
                if workflow_uuid and enabled:
                    try:
                        LOGGER.info(f"➕ Adding new job: {job_id}")
                        LOGGER.info(f"   🔄 Workflow: {workflow_uuid}")
                        LOGGER.info(f"   ⏰ Cron: {cron_expr}")

                        trigger = CronTrigger.from_crontab(cron_expr, timezone=timezone or "UTC")

                        scheduler.add_job(
                            func=execute_celery_task,
                            trigger=trigger,
                            id=job_id,
                            args=[str(project_id) if project_id else "", str(workflow_uuid), job_type, args or ""],
                            name=f"Workflow {job_type} - {workflow_uuid}",
                            replace_existing=True,
                        )

                        LOGGER.info(f"✅ Successfully added job {job_id}")

                    except Exception as e:
                        LOGGER.error(f"❌ Failed to add job {job_id}: {e}")

        # Remove jobs that no longer exist in database
        for job_id in current_jobs:
            if job_id not in db_job_ids:
                try:
                    LOGGER.info(f"🗑️ Removing job: {job_id}")
                    scheduler.remove_job(job_id)
                    LOGGER.info(f"✅ Successfully removed job {job_id}")
                except Exception as e:
                    LOGGER.error(f"❌ Failed to remove job {job_id}: {e}")

        # Log summary
        new_jobs = db_job_ids - set(current_jobs.keys())
        removed_jobs = set(current_jobs.keys()) - db_job_ids

        if new_jobs or removed_jobs:
            LOGGER.info("🔄 Job sync complete:")
            LOGGER.info(f"   ➕ Added: {len(new_jobs)} jobs")
            LOGGER.info(f"   🗑️ Removed: {len(removed_jobs)} jobs")
            LOGGER.info(f"   📊 Total active: {len(db_job_ids)} jobs")

    except Exception as e:
        LOGGER.error(f"❌ Failed to sync jobs: {e}")


def main():
    """Main function to run APScheduler daemon"""

    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    LOGGER.info("🚀 Starting APScheduler daemon...")
    LOGGER.info(f"   🗄️  Database: {settings.ADA_DB_URL.split('@')[-1]}")  # Hide credentials
    LOGGER.info("   📋 Table: apscheduler_jobs")

    try:
        # Create and start scheduler
        scheduler = create_scheduler()

        LOGGER.info("✅ APScheduler daemon created successfully")

        # Add dynamic job synchronization to memory store (no serialization issues)
        scheduler.add_job(
            func=sync_jobs_with_database,
            args=[scheduler],
            trigger="interval",
            seconds=30,  # Sync every 30 seconds
            id="job_sync",
            name="Dynamic Job Sync",
            jobstore="memory",  # Use memory store for sync job
            replace_existing=True,
        )

        LOGGER.info("🔄 Added dynamic job sync (every 30 seconds)")

        # Start the scheduler
        scheduler.start()

        LOGGER.info("🎯 APScheduler daemon is now running with dynamic job loading!")
        LOGGER.info("📡 New jobs created via API will be automatically loaded")
        LOGGER.info("🛑 Press Ctrl+C to stop")

        # This will block and run the scheduler indefinitely

    except KeyboardInterrupt:
        LOGGER.info("⚠️  Received keyboard interrupt, shutting down...")
    except Exception as e:
        LOGGER.error(f"❌ APScheduler daemon failed: {str(e)}")
        sys.exit(1)
    finally:
        LOGGER.info("🛑 APScheduler daemon stopped")


if __name__ == "__main__":
    main()
