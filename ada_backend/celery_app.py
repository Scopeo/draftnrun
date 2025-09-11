import logging

from celery import Celery
from kombu import Queue

from settings import settings

LOGGER = logging.getLogger(__name__)

REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT
REDIS_PASSWORD = settings.REDIS_PASSWORD

if REDIS_HOST is None or REDIS_PORT is None or REDIS_PASSWORD is None:
    LOGGER.error("Redis configuration is incomplete. Please check your settings.")
    raise ValueError("Redis host, port, or password is not set in the configuration for Celery.")

REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"

LOGGER.info(f"Configuring Celery with Redis at {REDIS_HOST}:{REDIS_PORT}")

# Create Celery app
celery_app = Celery("ada_backend")

# Celery configuration
celery_app.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=3600,  # Remove the task from redis after 1 hour
    # Task routing
    task_routes={
        "execute_scheduled_workflow": {"queue": "scheduled_workflows"},
    },
    # Define queues
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("scheduled_workflows"),  # For scheduled workflow execution
    ),
    # Worker configuration
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,
)

# Auto-discover tasks
celery_app.autodiscover_tasks(
    [
        "ada_backend.tasks.workflow_tasks",  # Workflow execution tasks
    ]
)

if __name__ == "__main__":
    celery_app.start()
