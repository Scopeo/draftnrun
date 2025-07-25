import logging
from typing import Dict, Any, Optional
from datetime import datetime
from celery.schedules import crontab

from ada_backend.celery_app import celery_app
from engine.agent.triggers.utils import validate_cron_expression, convert_cron_to_utc, validate_timezone

LOGGER = logging.getLogger(__name__)


def register_schedule_direct(
    schedule_name: str,
    cron_expression: str,
    project_id: str,
    graph_runner_id: str,
    timezone: str = "UTC",
    schedule_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Register a new scheduled workflow directly in Beat configuration.

    Args:
        schedule_name: Unique name for the schedule
        cron_expression: Cron expression for scheduling (in user timezone)
        project_id: UUID string of the project
        graph_runner_id: UUID string of the graph runner
        timezone: Timezone for schedule execution
        schedule_id: Optional UUID string for tracking

    Returns:
        dict: Registration result with status
    """
    LOGGER.info(
        f"Registering schedule directly: {schedule_name} with cron '{cron_expression}' in timezone '{timezone}'"
    )

    try:
        # Validate timezone first
        timezone_validation = validate_timezone(timezone)
        if timezone_validation["status"] != "SUCCESS":
            return {
                "status": "FAILED",
                "schedule_name": schedule_name,
                "error": f"Invalid timezone: {timezone_validation['error']}",
            }

        timezone_label = timezone_validation["label"]
        LOGGER.info(f"Using timezone: {timezone_label}")

        # Convert cron expression from user timezone to UTC
        conversion_result = convert_cron_to_utc(cron_expression, timezone)
        if conversion_result["status"] != "SUCCESS":
            return {"status": "FAILED", "schedule_name": schedule_name, "error": conversion_result["error"]}

        utc_cron = conversion_result["utc_cron"]
        original_description = conversion_result["original_description"]
        utc_description = conversion_result["utc_description"]
        timezone_offset = conversion_result["timezone_offset"]

        LOGGER.info(f"Timezone conversion: {cron_expression} ({timezone_label}) -> {utc_cron} (UTC)")
        LOGGER.info(f"Schedule description: {original_description} -> {utc_description}")

        # Validate the UTC cron expression
        validation_result = validate_cron_expression(utc_cron)
        if validation_result["status"] != "SUCCESS":
            return {
                "status": "FAILED",
                "schedule_name": schedule_name,
                "error": f"Invalid UTC cron expression: {validation_result['error']}",
            }

        # Parse the UTC cron expression components for Celery
        utc_parts = utc_cron.split()
        if len(utc_parts) != 5:
            return {
                "status": "FAILED",
                "schedule_name": schedule_name,
                "error": f"Invalid cron format: {utc_cron} (expected 5 parts)",
            }

        minute, hour, day, month, day_of_week = utc_parts

        # Create crontab schedule with proper UTC cron components
        schedule = crontab(
            minute=minute,
            hour=hour,
            day_of_month=day,
            month_of_year=month,
            day_of_week=day_of_week,
        )

        # DIRECT Beat configuration modification - immediate effect
        celery_app.conf.beat_schedule[schedule_name] = {
            "task": "execute_scheduled_workflow",
            "schedule": schedule,
            "args": (project_id, graph_runner_id, schedule_id),
            "options": {"queue": "scheduled_workflows", "expires": 3600},
        }

        LOGGER.info(f"Successfully registered schedule directly: {schedule_name}")
        LOGGER.info(f"Original: {original_description} ({timezone_label})")
        LOGGER.info(f"UTC Schedule: {utc_description} (UTC)")

        return {
            "status": "SUCCESS",
            "schedule_name": schedule_name,
            "original_description": original_description,
            "utc_description": utc_description,
            "timezone_offset": timezone_offset,
            "timezone_label": timezone_label,
            "original_cron": cron_expression,
            "utc_cron": utc_cron,
            "method": "direct_configuration",
            "message": f"Schedule '{schedule_name}' registered directly: "
            f"{original_description} ({timezone_label}) -> {utc_description} (UTC)",
        }

    except Exception as e:
        error_msg = f"Failed to register schedule '{schedule_name}' directly: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {"status": "FAILED", "schedule_name": schedule_name, "error": error_msg}


def unregister_schedule_direct(schedule_name: str) -> Dict[str, Any]:
    """
    Unregister a scheduled workflow directly from Beat configuration.

    Args:
        schedule_name: Name of the schedule to remove

    Returns:
        dict: Unregistration result with status
    """
    LOGGER.info(f"Unregistering schedule directly: {schedule_name}")

    try:
        # DIRECT Beat configuration modification - immediate effect
        if schedule_name in celery_app.conf.beat_schedule:
            del celery_app.conf.beat_schedule[schedule_name]

            LOGGER.info(f"Successfully unregistered schedule directly: {schedule_name}")
            return {
                "status": "SUCCESS",
                "schedule_name": schedule_name,
                "method": "direct_configuration",
                "message": f"Schedule '{schedule_name}' unregistered directly",
            }
        else:
            LOGGER.warning(f"Schedule not found: {schedule_name}")
            return {
                "status": "NOT_FOUND",
                "schedule_name": schedule_name,
                "message": f"Schedule '{schedule_name}' not found",
            }

    except Exception as e:
        error_msg = f"Failed to unregister schedule '{schedule_name}' directly: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {"status": "FAILED", "schedule_name": schedule_name, "error": error_msg}


def update_schedule_direct(
    schedule_name: str,
    cron_expression: str,
    project_id: str,
    graph_runner_id: str,
    timezone: str = "UTC",
    schedule_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update an existing scheduled workflow directly.

    Args:
        schedule_name: Name of the schedule to update
        cron_expression: New cron expression (in user timezone)
        project_id: UUID string of the project
        graph_runner_id: UUID string of the graph runner
        timezone: Timezone for schedule execution
        schedule_id: Optional UUID string for tracking

    Returns:
        dict: Update result with status
    """
    LOGGER.info(f"Updating schedule directly: {schedule_name} with cron '{cron_expression}' in timezone '{timezone}'")

    try:
        # First unregister the old schedule
        unregister_result = unregister_schedule_direct(schedule_name)
        if unregister_result["status"] == "FAILED":
            return unregister_result

        # Then register with new parameters
        register_result = register_schedule_direct(
            schedule_name=schedule_name,
            cron_expression=cron_expression,
            project_id=project_id,
            graph_runner_id=graph_runner_id,
            timezone=timezone,
            schedule_id=schedule_id,
        )

        if register_result["status"] == "SUCCESS":
            register_result["message"] = f"Schedule '{schedule_name}' updated directly"
            register_result["method"] = "direct_configuration"

        return register_result

    except Exception as e:
        error_msg = f"Failed to update schedule '{schedule_name}' directly: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {"status": "FAILED", "schedule_name": schedule_name, "error": error_msg}


def list_schedules_direct() -> Dict[str, Any]:
    """
    List all registered scheduled workflows directly from Beat configuration.

    Returns:
        dict: List of schedules with status
    """
    LOGGER.info("Listing all registered schedules directly")

    try:
        schedules = []
        for name, config in celery_app.conf.beat_schedule.items():
            if config.get("task") == "execute_scheduled_workflow":
                schedules.append(
                    {
                        "name": name,
                        "task": config["task"],
                        "schedule": str(config["schedule"]),
                        "args": config.get("args", []),
                        "queue": config.get("options", {}).get("queue", "default"),
                    }
                )

        LOGGER.info(f"Found {len(schedules)} registered schedules")
        return {"status": "SUCCESS", "schedules": schedules, "count": len(schedules), "method": "direct_configuration"}

    except Exception as e:
        error_msg = f"Failed to list schedules directly: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {"status": "FAILED", "error": error_msg}


def health_check_schedules_direct() -> Dict[str, Any]:
    """
    Health check for the scheduling system using direct access.

    Returns:
        dict: Health check result with detailed component status
    """
    LOGGER.info("Performing direct health check on scheduling system")

    try:
        # 1. Check Celery Worker connection and queues
        redis_accessible = True
        worker_count = 0
        queue_active = False
        active_queues = {}

        try:
            inspector = celery_app.control.inspect()
            active_queues = inspector.active_queues() or {}

            # Check if scheduled_workflows queue is active
            if active_queues:
                worker_count = len(active_queues)
                for worker, queues in active_queues.items():
                    if any(q["name"] == "scheduled_workflows" for q in queues):
                        queue_active = True
                        break
        except Exception as e:
            redis_accessible = False
            LOGGER.error(f"Redis/Worker connection failed: {str(e)}")

        # 2. Count registered schedules (direct access - always works)
        schedule_count = len(
            [
                name
                for name, config in celery_app.conf.beat_schedule.items()
                if config.get("task") == "execute_scheduled_workflow"
            ]
        )

        # 3. Beat is running if we can access configuration
        beat_accessible = True

        # 4. Determine overall health status
        if not redis_accessible:
            status = "DEGRADED"  # Can manage schedules, but can't execute
        elif not queue_active:
            status = "DEGRADED"  # Can manage schedules, but no workers to execute
        else:
            status = "HEALTHY"

        health_status = {
            "status": status,
            "components": {
                "redis_accessible": redis_accessible,
                "celery_beat_accessible": beat_accessible,
                "workers_active": queue_active,
                "scheduled_workflows_queue_active": queue_active,
                "direct_management": True,  # Always true for direct management
            },
            "metrics": {
                "worker_count": worker_count,
                "registered_schedules": schedule_count,
                "active_queues": list(active_queues.keys()) if active_queues else [],
            },
            "method": "direct_configuration",
            "timestamp": datetime.now().isoformat(),
        }

        LOGGER.info(f"Direct health check completed: {health_status}")
        return health_status

    except Exception as e:
        error_msg = f"Direct health check failed: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {
            "status": "UNHEALTHY",
            "error": error_msg,
            "components": {
                "redis_accessible": False,
                "celery_beat_accessible": False,
                "workers_active": False,
                "scheduled_workflows_queue_active": False,
                "direct_management": False,
            },
            "metrics": {
                "worker_count": 0,
                "registered_schedules": 0,
                "active_queues": [],
            },
            "method": "direct_configuration",
        }
