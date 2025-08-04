"""
Django sync module for synchronizing scheduled_workflows with django-celery-beat tables.
Handles the bridge between our backend scheduling system and django-celery-beat execution engine.
"""

import json
import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ada_backend.database.models import ScheduledWorkflow
from ada_backend.schemas.schedule_schema import ScheduleSyncResponse

LOGGER = logging.getLogger(__name__)


def _configure_django():
    """Configure Django for django-celery-beat operations."""
    import django
    from django.conf import settings as django_settings

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ada_backend.django_scheduler.django_settings")

    if not django_settings.configured:
        django.setup()


def _get_django_models():
    """Get Django models after ensuring Django is configured."""
    _configure_django()
    from ada_backend.django_scheduler.models import CrontabSchedule, PeriodicTask, PeriodicTasks

    return CrontabSchedule, PeriodicTask, PeriodicTasks


def create_or_update_crontab_schedule(cron_expression: str, timezone: str = "UTC") -> Any:
    """
    Create or get existing crontab schedule in django-celery-beat format.

    Args:
        cron_expression: Cron expression (e.g., "*/2 * * * *")
        timezone: Timezone for the schedule

    Returns:
        CrontabSchedule instance
    """
    CrontabSchedule, _, _ = _get_django_models()

    # Parse cron expression
    parts = cron_expression.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expression}")

    minute, hour, day_of_month, month_of_year, day_of_week = parts

    # Check if this exact crontab already exists
    existing_crontab = CrontabSchedule.objects.filter(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
        timezone=timezone,
    ).first()

    if existing_crontab:
        LOGGER.info(f"Reusing existing crontab schedule: {existing_crontab.id}")
        return existing_crontab

    # Create new crontab schedule
    crontab_schedule = CrontabSchedule.objects.create(
        minute=minute,
        hour=hour,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        day_of_week=day_of_week,
        timezone=timezone,
    )

    LOGGER.info(f"Created new crontab schedule: {crontab_schedule.id} for {cron_expression}")
    return crontab_schedule


def update_periodic_tasks_changed():
    """
    Update the periodic tasks changed timestamp to trigger Celery Beat to reload schedules.
    """
    _, _, PeriodicTasks = _get_django_models()

    # Get or create the periodic tasks record
    periodic_tasks, created = PeriodicTasks.objects.get_or_create(ident=1)

    # Update the timestamp with timezone-aware datetime
    periodic_tasks.last_update = datetime.now(timezone.utc)
    periodic_tasks.save()

    LOGGER.info("Updated periodic tasks changed timestamp")


def sync_to_django(session: Session, scheduled_workflow_id: int) -> ScheduleSyncResponse:
    """
    Sync a scheduled_workflow record to django-celery-beat tables.

    Args:
        session: Database session
        scheduled_workflow_id: ID of the scheduled_workflow record

    Returns:
        Sync response with details

    Raises:
        ValueError: If workflow not found or sync fails
    """
    try:
        # Get the scheduled workflow
        scheduled_workflow = (
            session.query(ScheduledWorkflow).filter(ScheduledWorkflow.id == scheduled_workflow_id).first()
        )

        if not scheduled_workflow:
            raise ValueError(f"ScheduledWorkflow with id {scheduled_workflow_id} not found")

        # Use the scheduling fields directly
        cron_expression = scheduled_workflow.cron_expression
        timezone_str = scheduled_workflow.timezone
        enabled = scheduled_workflow.enabled

        if not cron_expression:
            raise ValueError("cron_expression is required")

        # Configure Django
        _configure_django()
        CrontabSchedule, PeriodicTask, PeriodicTasks = _get_django_models()

        # Create or get crontab schedule
        crontab_schedule = create_or_update_crontab_schedule(cron_expression, timezone_str)

        # Generate unique task name
        task_name = f"sync_workflow_{scheduled_workflow.uuid}"

        # Check if periodic task already exists by scheduled_workflow_uuid using raw SQL
        existing_task = PeriodicTask.objects.raw(
            """
            SELECT * FROM django_beat_cron_scheduler.django_celery_beat_periodictask 
            WHERE scheduled_workflow_uuid = %s
        """,
            [str(scheduled_workflow.uuid)],
        )

        # Get the first result if any
        existing_task = list(existing_task)[0] if existing_task else None

        if existing_task:
            # Update existing task
            existing_task.crontab = crontab_schedule
            existing_task.enabled = enabled
            existing_task.task = "execute_scheduled_workflow"  # Update task name
            existing_task.args = json.dumps(
                [
                    str(scheduled_workflow.project_id) if scheduled_workflow.project_id else "",
                    str(scheduled_workflow.uuid),
                    scheduled_workflow.type.value,
                    scheduled_workflow.args,
                ]
            )
            existing_task.kwargs = json.dumps({})  # No kwargs needed
            existing_task.save()

            # Update the scheduled_workflow_uuid field using raw SQL
            import psycopg2
            from settings import settings

            db_params = {
                "dbname": settings.ADA_DB_NAME,
                "user": settings.ADA_DB_USER,
                "password": settings.ADA_DB_PASSWORD,
                "host": settings.ADA_DB_HOST,
                "port": settings.ADA_DB_PORT,
            }

            conn = psycopg2.connect(**db_params)
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE django_beat_cron_scheduler.django_celery_beat_periodictask 
                SET scheduled_workflow_uuid = %s
                WHERE id = %s
            """,
                (str(scheduled_workflow.uuid), existing_task.id),
            )

            conn.commit()
            cursor.close()
            conn.close()

            periodic_task = existing_task
            action = "updated"
        else:
            # Create new task
            periodic_task = PeriodicTask.objects.create(
                name=f"sync_workflow_{scheduled_workflow.uuid}",
                task="execute_scheduled_workflow",  # Fixed: match the actual task name
                crontab=crontab_schedule,
                args=json.dumps(
                    [
                        str(scheduled_workflow.project_id) if scheduled_workflow.project_id else "",
                        str(scheduled_workflow.uuid),
                        scheduled_workflow.type.value,
                        scheduled_workflow.args,
                    ]
                ),
                kwargs=json.dumps({}),  # No kwargs needed
                queue="scheduled_workflows",  # Fixed: match the task routing
                enabled=enabled,
                description=f"Scheduled workflow {scheduled_workflow.type.value} for {scheduled_workflow.uuid}",
            )

            # Set the scheduled_workflow_uuid field using raw SQL
            import psycopg2
            from settings import settings

            db_params = {
                "dbname": settings.ADA_DB_NAME,
                "user": settings.ADA_DB_USER,
                "password": settings.ADA_DB_PASSWORD,
                "host": settings.ADA_DB_HOST,
                "port": settings.ADA_DB_PORT,
            }

            conn = psycopg2.connect(**db_params)
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE django_beat_cron_scheduler.django_celery_beat_periodictask 
                SET scheduled_workflow_uuid = %s
                WHERE id = %s
            """,
                (str(scheduled_workflow.uuid), periodic_task.id),
            )

            conn.commit()
            cursor.close()
            conn.close()

            action = "created"

        # Update change tracking
        update_periodic_tasks_changed()

        LOGGER.info(f"{action.capitalize()} django-celery-beat task for scheduled_workflow {scheduled_workflow.uuid}")

        return ScheduleSyncResponse(
            schedule_id=scheduled_workflow_id,
            schedule_uuid=scheduled_workflow.uuid,
            action=action,
            periodic_task_id=periodic_task.id,
            message=f"Schedule {action} successfully",
        )

    except Exception as e:
        error_msg = f"Failed to sync scheduled_workflow: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        raise ValueError(error_msg) from e


def sync_all_enabled_workflows(session: Session) -> Dict[str, Any]:
    """
    Sync all enabled scheduled workflows to django-celery-beat.

    Args:
        session: Database session

    Returns:
        Dict with sync results
    """
    from ada_backend.repositories.schedule_repository import get_enabled_scheduled_workflows

    workflows = get_enabled_scheduled_workflows(session)

    results = {"total": len(workflows), "successful": 0, "failed": 0, "errors": []}

    for workflow in workflows:
        try:
            sync_result = sync_to_django(session, workflow.id)
            results["successful"] += 1
        except ValueError as e:
            results["failed"] += 1
            results["errors"].append({"workflow_id": workflow.id, "error": str(e)})
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"workflow_id": workflow.id, "error": str(e)})

    LOGGER.info(f"Sync completed: {results['successful']} successful, {results['failed']} failed")

    return results
