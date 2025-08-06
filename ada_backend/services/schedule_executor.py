"""
Shared task functions for APScheduler.
These functions are used by both the scheduler service and the APScheduler daemon.
"""

import logging
from datetime import datetime
from ada_backend.celery_app import celery_app

LOGGER = logging.getLogger(__name__)


def execute_celery_task(project_id: str, workflow_uuid: str, type_value: str, args: str):
    """Function that gets executed by APScheduler when jobs are due"""
    execution_time = datetime.now()

    LOGGER.info(f"🚀 APScheduler executing job at {execution_time.isoformat()}")
    LOGGER.info(f"   📋 Workflow UUID: {workflow_uuid}")
    LOGGER.info(f"   🏢 Project ID: {project_id}")
    LOGGER.info(f"   🔧 Type: {type_value}")
    LOGGER.info(f"   📄 Args: {args}")

    try:
        # Send task to Celery worker
        result = celery_app.send_task(
            "execute_scheduled_workflow",
            args=[project_id, workflow_uuid, type_value, args],
            queue="scheduled_workflows",
        )

        LOGGER.info("✅ Successfully sent to Celery queue 'scheduled_workflows'")
        LOGGER.info(f"   🆔 Celery Task ID: {result.id}")
        LOGGER.info(f"   🕐 Triggered at: {execution_time.isoformat()}")
        LOGGER.info(f"   🔄 Workflow: {workflow_uuid}")

    except Exception as e:
        LOGGER.error(f"❌ Failed to trigger Celery task for workflow {workflow_uuid}")
        LOGGER.error(f"   🕐 Failed at: {execution_time.isoformat()}")
        LOGGER.error(f"   ⚠️  Error: {str(e)}")
        raise  # Re-raise to let APScheduler handle the failure
