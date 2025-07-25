"""
Database-driven schedule management service for Draft'n Run.
Uses django-celery-beat for persistent, database-driven scheduling.
Integrates with cron API key management for secure HTTP-based workflow execution.
Uses django-celery-beat tables as the single source of truth.
"""

import json
import logging
import os
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ada_backend.database.models import EnvType
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.services.agent_runner_service import find_cron_scheduler_components, get_component_params
from ada_backend.services.cron_api_key_service import (
    generate_cron_api_key_for_project,
    update_cron_api_key_for_project,
    cleanup_cron_api_keys_for_project,
    get_existing_cron_api_key,
)
from engine.agent.triggers.utils import convert_cron_to_utc
from ada_backend.database.models import ComponentInstance, Component, GraphRunnerNode, ProjectEnvironmentBinding

LOGGER = logging.getLogger(__name__)

# System user ID for cron operations (placeholder - should be a real system user in production)
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


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
    from django_celery_beat.models import CrontabSchedule, PeriodicTask, PeriodicTasks

    return CrontabSchedule, PeriodicTask, PeriodicTasks


def generate_schedule_name(project_id: UUID, graph_runner_id: UUID, scheduler_id: UUID) -> str:
    """
    Generate a unique schedule name for django-celery-beat.

    Args:
        project_id: Project UUID
        graph_runner_id: Graph runner UUID
        scheduler_id: Scheduler component instance UUID

    Returns:
        Unique schedule name string
    """
    return f"schedule_{str(project_id)[:8]}_{str(graph_runner_id)[:8]}_{str(scheduler_id)[:8]}"


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
        timezone=timezone,  # Use timezone directly
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
        timezone=timezone,  # Use timezone directly
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


def ensure_cron_api_key_for_project(session: Session, project_id: UUID) -> Dict[str, Any]:
    """
    Ensure a cron API key exists for the project.

    Args:
        session: Database session
        project_id: Project UUID

    Returns:
        Dict with API key status
    """
    # Check if cron API key already exists
    existing_key = get_existing_cron_api_key(session, project_id)
    if existing_key:
        return {"status": "EXISTS", "key_name": existing_key.name, "cron_job_uuid": existing_key.id}

    # Generate new cron API key
    return generate_cron_api_key_for_project(session=session, project_id=project_id, creator_user_id=SYSTEM_USER_ID)


def create_periodic_task_for_scheduler(
    project_id: UUID,
    graph_runner_id: UUID,
    cron_scheduler_component_id: UUID,
    cron_expression: str,
    timezone_str: str = "UTC",
    enabled: bool = True,
) -> Dict[str, Any]:
    """
    Create a django-celery-beat periodic task for a scheduler.

    Args:
        project_id: Project UUID
        graph_runner_id: Graph runner UUID
        cron_scheduler_component_id: Scheduler component instance UUID
        cron_expression: Cron expression
        timezone_str: Timezone for the schedule
        enabled: Whether the schedule is enabled

    Returns:
        Dict with creation result
    """
    _, PeriodicTask, _ = _get_django_models()

    try:
        # Validate and convert cron expression to UTC
        conversion_result = convert_cron_to_utc(cron_expression, timezone_str)
        if conversion_result["status"] != "SUCCESS":
            return {"status": "FAILED", "error": f"Invalid cron expression: {conversion_result['error']}"}

        utc_cron = conversion_result["utc_cron"]

        # Generate unique task name
        schedule_name = generate_schedule_name(project_id, graph_runner_id, cron_scheduler_component_id)

        # 1. Create the crontab schedule
        crontab_schedule = create_or_update_crontab_schedule(utc_cron, "UTC")

        # 2. Create the periodic task
        task_args = [str(project_id), str(graph_runner_id), str(cron_scheduler_component_id)]
        periodic_task = PeriodicTask.objects.create(
            name=schedule_name,
            task="execute_scheduled_workflow",
            crontab=crontab_schedule,
            args=json.dumps(task_args),
            kwargs=json.dumps(
                {
                    "cron_expression": cron_expression,
                    "timezone": timezone_str,
                    "user_timezone": timezone_str,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
            queue="scheduled_workflows",
            enabled=enabled,
            description=f"Scheduled workflow execution for project {project_id}",
        )

        # 3. Update change tracking
        update_periodic_tasks_changed()

        LOGGER.info(f"Created django-celery-beat periodic task: {schedule_name}")

        return {
            "status": "SUCCESS",
            "periodic_task_id": periodic_task.id,
            "task_name": schedule_name,
            "crontab_id": crontab_schedule.id,
            "utc_cron": utc_cron,
            "message": "Schedule created successfully",
        }

    except Exception as e:
        error_msg = f"Failed to create periodic task: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {"status": "FAILED", "error": error_msg}


def create_schedules_for_graph(session: Session, project_id: UUID, graph_runner_id: UUID) -> Dict[str, Any]:
    """
    Create scheduled workflows for all CRON_SCHEDULER components in a graph.
    Only creates schedules if the graph is in PRODUCTION environment.
    Ensures cron API key exists before creating schedules.
    Uses django-celery-beat tables as the single source of truth.

    Args:
        session: Database session
        project_id: Project UUID
        graph_runner_id: Graph runner UUID

    Returns:
        Dict with creation results
    """
    LOGGER.info(f"Creating schedules for graph {graph_runner_id} in project {project_id}")

    # Check if graph is in production environment
    env_relationship = get_env_relationship_by_graph_runner_id(session, graph_runner_id)
    if not env_relationship or env_relationship.environment != EnvType.PRODUCTION:
        LOGGER.info(f"Graph {graph_runner_id} is not in PRODUCTION environment - skipping schedule creation")
        return {"status": "SKIPPED", "reason": "Graph not in PRODUCTION environment", "schedules_created": 0}

    # Find all CRON_SCHEDULER components
    schedulers = find_cron_scheduler_components(session, graph_runner_id)
    if not schedulers:
        LOGGER.info(f"No CRON_SCHEDULER components found in graph {graph_runner_id}")
        return {"status": "SUCCESS", "message": "No schedulers found", "schedules_created": 0}

    # Ensure cron API key exists for the project
    api_key_result = ensure_cron_api_key_for_project(session, project_id)
    if api_key_result["status"] not in ["SUCCESS", "EXISTS"]:
        error_msg = (
            f"Failed to ensure cron API key for project {project_id}: {api_key_result.get('error', 'Unknown error')}"
        )
        LOGGER.error(error_msg)
        return {"status": "FAILED", "error": error_msg, "schedules_created": 0, "api_key_error": api_key_result}

    LOGGER.info(f"Cron API key ready for project {project_id}: {api_key_result['status']}")

    created_schedules = []
    failed_schedules = []

    for scheduler in schedulers:
        try:
            # Get scheduler configuration
            params = get_component_params(session, scheduler.id)
            cron_expression = params.get("cron_expression", "0 9 * * *")
            timezone_str = params.get("timezone", "UTC")
            enabled = params.get("enabled", True)

            if not enabled:
                LOGGER.info(f"Scheduler {scheduler.id} is disabled - skipping")
                continue

            # Create the periodic task
            result = create_periodic_task_for_scheduler(
                project_id=project_id,
                graph_runner_id=graph_runner_id,
                cron_scheduler_component_id=scheduler.id,
                cron_expression=cron_expression,
                timezone_str=timezone_str,
                enabled=enabled,
            )

            if result["status"] == "SUCCESS":
                created_schedules.append(
                    {
                        "scheduler_id": str(scheduler.id),
                        "periodic_task_id": result["periodic_task_id"],
                        "task_name": result["task_name"],
                        "cron_expression": cron_expression,
                        "timezone": timezone_str,
                        "method": "django_celery_beat_only",
                        "crontab_id": result["crontab_id"],
                        "utc_cron": result["utc_cron"],
                    }
                )
                LOGGER.info(f"Successfully created schedule for scheduler {scheduler.id}")
            else:
                failed_schedules.append(
                    {"scheduler_id": str(scheduler.id), "error": result.get("error", "Unknown error")}
                )
                LOGGER.error(f"Failed to create schedule for scheduler {scheduler.id}: {result.get('error')}")

        except Exception as e:
            error_msg = f"Exception creating schedule for scheduler {scheduler.id}: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            failed_schedules.append({"scheduler_id": str(scheduler.id), "error": error_msg})

    LOGGER.info(f"Schedule creation completed for new graph {graph_runner_id}")
    return {
        "status": "SUCCESS" if not failed_schedules else "PARTIAL",
        "schedules_created": len(created_schedules),
        "schedules_failed": len(failed_schedules),
        "created": created_schedules,
        "failed": failed_schedules,
        "method": "django_celery_beat_only",
        "api_key_info": api_key_result,
    }


def cleanup_schedules_for_graph(
    session: Session, graph_runner_id: UUID, cleanup_api_key: bool = False
) -> Dict[str, Any]:
    """
    Remove all scheduled workflows associated with a graph runner.
    Uses django-celery-beat database tables.

    Args:
        session: Database session
        graph_runner_id: Graph runner UUID
        cleanup_api_key: Whether to clean up cron API keys

    Returns:
        Dict with cleanup results
    """
    CrontabSchedule, PeriodicTask, _ = _get_django_models()

    LOGGER.info(f"Cleaning up schedules for graph {graph_runner_id}")

    removed_schedules = []
    failed_removals = []

    try:
        # Find all periodic tasks for this graph by checking task names
        periodic_tasks = PeriodicTask.objects.filter(task="execute_scheduled_workflow")

        for periodic_task in periodic_tasks:
            try:
                # Check if this task belongs to our graph by parsing the name
                if periodic_task.name.startswith("schedule_"):
                    # Parse the task name to extract graph_runner_id
                    name_parts = periodic_task.name.split("_")
                    if len(name_parts) >= 3:
                        task_graph_runner_id = name_parts[2]  # Extract graph runner ID from name
                        if task_graph_runner_id == str(graph_runner_id)[:8]:
                            # Store crontab ID for potential cleanup
                            crontab_id = periodic_task.crontab.id if periodic_task.crontab else None

                            # Delete the periodic task
                            periodic_task.delete()

                            # Check if this crontab is used by other tasks
                            if crontab_id:
                                other_tasks = PeriodicTask.objects.filter(crontab_id=crontab_id).count()

                                # If no other tasks use this crontab, delete it
                                if other_tasks == 0:
                                    crontab_schedule = CrontabSchedule.objects.filter(id=crontab_id).first()
                                    if crontab_schedule:
                                        crontab_schedule.delete()
                                        LOGGER.info(f"Deleted unused crontab schedule: {crontab_id}")

                            removed_schedules.append(
                                {
                                    "periodic_task_id": periodic_task.id,
                                    "task_name": periodic_task.name,
                                    "crontab_id": crontab_id,
                                }
                            )

                            LOGGER.info(f"Removed periodic task: {periodic_task.name}")

            except Exception as e:
                error_msg = f"Failed to remove periodic task {periodic_task.id}: {str(e)}"
                LOGGER.error(error_msg, exc_info=True)
                failed_removals.append({"periodic_task_id": periodic_task.id, "error": error_msg})

        # Update change tracking
        update_periodic_tasks_changed()

    except Exception as e:
        error_msg = f"Failed to cleanup schedules for graph {graph_runner_id}: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        failed_removals.append({"error": error_msg})

    # Handle API key cleanup if requested
    api_key_cleanup_result = {"status": "SKIPPED", "reason": "Not requested"}
    if cleanup_api_key:
        try:
            # Get project_id from graph environment relationship
            env_relationship = get_env_relationship_by_graph_runner_id(session, graph_runner_id)
            if env_relationship:
                project_id = env_relationship.project_id

                # Check if there are any other active schedulers in the project
                has_other_schedulers = has_active_schedulers_in_project(session, project_id)

                if not has_other_schedulers:
                    api_key_cleanup_result = cleanup_cron_api_keys_for_project(
                        session=session, project_id=project_id, revoker_user_id=SYSTEM_USER_ID
                    )
                    LOGGER.info(
                        f"Cleaned up cron API keys for project {project_id}: {api_key_cleanup_result['status']}"
                    )
                else:
                    LOGGER.info(f"Other schedulers exist in project {project_id} - keeping cron API keys")
                    api_key_cleanup_result = {"status": "SKIPPED", "reason": "Other schedulers exist in project"}
            else:
                LOGGER.warning(f"No environment relationship found for graph {graph_runner_id}")
                api_key_cleanup_result = {"status": "SKIPPED", "reason": "No environment relationship found"}

        except Exception as e:
            error_msg = f"Failed to cleanup API keys: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            api_key_cleanup_result = {"status": "FAILED", "error": error_msg}

    return {
        "status": "SUCCESS" if not failed_removals else "PARTIAL",
        "schedules_removed": len(removed_schedules),
        "removals_failed": len(failed_removals),
        "removed": removed_schedules,
        "failed": failed_removals,
        "api_key_cleanup": api_key_cleanup_result,
        "method": "django_celery_beat_only",
    }


def get_schedules_for_project(session: Session, project_id: UUID) -> Dict[str, Any]:
    """
    Get all active schedules for a project using django-celery-beat tables.

    Args:
        session: Database session
        project_id: Project UUID

    Returns:
        Dict with schedule information
    """
    _, PeriodicTask, _ = _get_django_models()

    project_schedules = []

    try:
        # Query all periodic tasks
        periodic_tasks = PeriodicTask.objects.filter(task="execute_scheduled_workflow")

        for periodic_task in periodic_tasks:
            try:
                # Check if this task belongs to our project by parsing the name
                if periodic_task.name.startswith("schedule_"):
                    name_parts = periodic_task.name.split("_")
                    if len(name_parts) >= 2:
                        task_project_id = name_parts[1]  # Extract project ID from name
                        if task_project_id == str(project_id)[:8]:
                            # Parse task arguments to get more details
                            task_args = json.loads(periodic_task.args) if periodic_task.args else []
                            task_kwargs = json.loads(periodic_task.kwargs) if periodic_task.kwargs else {}

                            schedule_info = {
                                "periodic_task_id": periodic_task.id,
                                "task_name": periodic_task.name,
                                "project_id": str(project_id),
                                "graph_runner_id": task_args[1] if len(task_args) > 1 else None,
                                "scheduler_id": task_args[2] if len(task_args) > 2 else None,
                                "cron_expression": task_kwargs.get("cron_expression"),
                                "timezone": task_kwargs.get("timezone"),
                                "user_timezone": task_kwargs.get("user_timezone"),
                                "enabled": periodic_task.enabled,
                                "last_run_at": (
                                    periodic_task.last_run_at.isoformat() if periodic_task.last_run_at else None
                                ),
                                "total_run_count": periodic_task.total_run_count,
                                "queue": periodic_task.queue,
                                "created_at": task_kwargs.get("created_at"),
                                "method": "django_celery_beat_only",
                            }

                            # Get crontab information if available
                            if periodic_task.crontab:
                                schedule_info.update(
                                    {
                                        "crontab_id": periodic_task.crontab.id,
                                        "cron_minute": periodic_task.crontab.minute,
                                        "cron_hour": periodic_task.crontab.hour,
                                        "cron_day_of_month": periodic_task.crontab.day_of_month,
                                        "cron_month_of_year": periodic_task.crontab.month_of_year,
                                        "cron_day_of_week": periodic_task.crontab.day_of_week,
                                        "cron_timezone": periodic_task.crontab.timezone,
                                    }
                                )

                            project_schedules.append(schedule_info)

            except Exception as e:
                LOGGER.error(f"Failed to parse periodic task {periodic_task.id}: {str(e)}")

    except Exception as e:
        LOGGER.error(f"Failed to query schedules for project {project_id}: {str(e)}", exc_info=True)

    return {
        "status": "SUCCESS",
        "project_id": str(project_id),
        "schedules": project_schedules,
        "count": len(project_schedules),
        "method": "django_celery_beat_only",
    }


def has_active_schedulers_in_project(session: Session, project_id: UUID) -> bool:
    """
    Check if a project has any active CRON_SCHEDULER components in production.

    Args:
        session: Database session
        project_id: Project UUID

    Returns:
        True if project has active schedulers, False otherwise
    """
    try:
        # Find all CRON_SCHEDULER components in production graphs for this project
        schedulers = (
            session.query(ComponentInstance)
            .join(Component, ComponentInstance.component_id == Component.id)
            .join(GraphRunnerNode, GraphRunnerNode.node_id == ComponentInstance.id)
            .join(
                ProjectEnvironmentBinding,
                GraphRunnerNode.graph_runner_id == ProjectEnvironmentBinding.graph_runner_id,
            )
            .filter(
                Component.name == "Cron Scheduler",
                ProjectEnvironmentBinding.project_id == project_id,
                ProjectEnvironmentBinding.environment == EnvType.PRODUCTION,
            )
            .all()
        )

        # Check if any of these schedulers are enabled
        for scheduler in schedulers:
            params = get_component_params(session, scheduler.id)
            enabled = params.get("enabled", True)
            if enabled:
                LOGGER.info(f"Found active scheduler {scheduler.id} in project {project_id}")
                return True

        LOGGER.info(f"No active schedulers found in project {project_id}")
        return False

    except Exception as e:
        LOGGER.error(f"Error checking for active schedulers in project {project_id}: {str(e)}", exc_info=True)
        return False


def handle_scheduling_on_deployment(
    session: Session, graph_runner_id: UUID, project_id: UUID, previous_production_graph_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """
    Handle schedule management during deployment.
    Removes old schedules, updates cron API keys, and creates new schedules for production graph.
    Uses django-celery-beat database tables for persistent scheduling.

    Args:
        session: Database session
        graph_runner_id: New production graph runner UUID
        project_id: Project UUID
        previous_production_graph_id: Previous production graph UUID (if any)

    Returns:
        Dict with deployment scheduling results
    """
    LOGGER.info(
        f"Handling scheduling for deployment: project={project_id}, "
        f"new_graph={graph_runner_id}, old_graph={previous_production_graph_id}"
    )

    results = {"cleanup_results": None, "creation_results": None, "api_key_update": None, "status": "SUCCESS"}

    # 1. Clean up old schedules if previous production graph existed
    if previous_production_graph_id:
        try:
            results["cleanup_results"] = cleanup_schedules_for_graph(
                session, previous_production_graph_id, cleanup_api_key=False  # Don't cleanup API key yet
            )
            LOGGER.info(f"Cleanup completed for old graph {previous_production_graph_id}")
        except Exception as e:
            error_msg = f"Failed to cleanup old schedules: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            results["cleanup_error"] = error_msg
            results["status"] = "PARTIAL"

    # 2. Check if new graph has CRON_SCHEDULER components
    schedulers = find_cron_scheduler_components(session, graph_runner_id)
    if not schedulers:
        LOGGER.info(f"No CRON_SCHEDULER components in new graph {graph_runner_id}")

        # Check if the project has any other active schedulers
        has_other_schedulers = has_active_schedulers_in_project(session, project_id)

        if not has_other_schedulers:
            LOGGER.info(f"No active schedulers found in project {project_id} - cleaning up cron API keys")
            try:
                # Clean up cron API keys since no schedulers are active
                api_key_cleanup_result = cleanup_cron_api_keys_for_project(
                    session=session, project_id=project_id, revoker_user_id=SYSTEM_USER_ID
                )
                results["api_key_cleanup"] = api_key_cleanup_result
                LOGGER.info(f"Cleaned up cron API keys for project {project_id}: {api_key_cleanup_result['status']}")
            except Exception as e:
                error_msg = f"Failed to cleanup cron API keys: {str(e)}"
                LOGGER.error(error_msg, exc_info=True)
                results["api_key_cleanup_error"] = error_msg
                results["status"] = "PARTIAL"
        else:
            LOGGER.info(f"Other active schedulers exist in project {project_id} - keeping cron API keys")
            results["api_key_cleanup"] = {"status": "SKIPPED", "reason": "Other active schedulers exist in project"}

        return {
            **results,
            "creation_results": {
                "status": "SKIPPED",
                "reason": "No CRON_SCHEDULER components",
                "schedules_created": 0,
            },
        }

    # 3. Update cron API key for new deployment
    try:
        results["api_key_update"] = update_cron_api_key_for_project(
            session=session, project_id=project_id, creator_user_id=SYSTEM_USER_ID
        )
        LOGGER.info(f"API key update completed for project {project_id}: {results['api_key_update']['status']}")
    except Exception as e:
        error_msg = f"Failed to update cron API key: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        results["api_key_error"] = error_msg
        results["status"] = "PARTIAL"

    # 4. Create new schedules for the production graph
    try:
        results["creation_results"] = create_schedules_for_graph(session, project_id, graph_runner_id)
        LOGGER.info(f"Schedule creation completed for new graph {graph_runner_id}")
    except Exception as e:
        error_msg = f"Failed to create new schedules: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        results["creation_error"] = error_msg
        results["status"] = "PARTIAL"

    return results


def cleanup_schedules_for_project(session: Session, project_id: UUID, cleanup_api_key: bool = True) -> Dict[str, Any]:
    """
    Clean up all schedules for a project.

    Args:
        session: Database session
        project_id: Project UUID
        cleanup_api_key: Whether to clean up cron API keys (default: True)

    Returns:
        Dict with cleanup results
    """
    CrontabSchedule, PeriodicTask, _ = _get_django_models()

    LOGGER.info(f"Cleaning up all schedules for project {project_id}")

    try:
        # Find all periodic tasks for this project by checking task names
        periodic_tasks = PeriodicTask.objects.filter(task="execute_scheduled_workflow")

        total_removed = 0
        for periodic_task in periodic_tasks:
            try:
                # Check if this task belongs to our project by parsing the name
                if periodic_task.name.startswith("schedule_"):
                    name_parts = periodic_task.name.split("_")
                    if len(name_parts) >= 2:
                        task_project_id = name_parts[1]  # Extract project ID from name
                        if task_project_id == str(project_id)[:8]:
                            # Store crontab ID for potential cleanup
                            crontab_id = periodic_task.crontab.id if periodic_task.crontab else None

                            # Delete the periodic task
                            periodic_task.delete()

                            # Check if this crontab is used by other tasks
                            if crontab_id:
                                other_tasks = PeriodicTask.objects.filter(crontab_id=crontab_id).count()

                                # If no other tasks use this crontab, delete it
                                if other_tasks == 0:
                                    crontab_schedule = CrontabSchedule.objects.filter(id=crontab_id).first()
                                    if crontab_schedule:
                                        crontab_schedule.delete()

                            total_removed += 1

            except Exception as e:
                LOGGER.error(f"Failed to remove periodic task {periodic_task.id}: {str(e)}")

        # Update change tracking
        update_periodic_tasks_changed()

        LOGGER.info(f"Cleaned up {total_removed} schedules for project {project_id}")

        # Handle API key cleanup
        api_key_cleanup_result = {"status": "SKIPPED", "reason": "Not requested"}
        if cleanup_api_key and total_removed > 0:
            try:
                api_key_cleanup_result = cleanup_cron_api_keys_for_project(
                    session=session, project_id=project_id, revoker_user_id=SYSTEM_USER_ID
                )
                LOGGER.info(f"Cleaned up cron API keys for project {project_id}: {api_key_cleanup_result['status']}")
            except Exception as e:
                error_msg = f"Failed to cleanup API keys: {str(e)}"
                LOGGER.error(error_msg, exc_info=True)
                api_key_cleanup_result = {"status": "FAILED", "error": error_msg}

        return {
            "status": "SUCCESS",
            "schedules_removed": total_removed,
            "api_key_cleanup": api_key_cleanup_result,
            "method": "django_celery_beat_only",
        }

    except Exception as e:
        error_msg = f"Failed to cleanup schedules for project {project_id}: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {"status": "FAILED", "error": error_msg}
