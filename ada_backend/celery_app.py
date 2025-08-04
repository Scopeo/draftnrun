import logging
import os

from celery import Celery
from celery.schedules import crontab
from kombu import Queue
import django
from django.conf import settings as django_settings

from settings import settings

# Configure Django for django-celery-beat
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ada_backend.django_scheduler.django_settings")

if not django_settings.configured:
    django.setup()
    logging.getLogger(__name__).info("Django configured successfully for django-celery-beat")

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
        "cleanup_old_executions": {"queue": "default"},
        "ada_backend.tasks.test_tasks.*": {"queue": "scheduled_tasks"},
    },
    # Define queues
    task_default_queue="default",
    task_queues=(
        Queue("default"),
        Queue("scheduled_workflows"),  # For scheduled workflow execution
        Queue("scheduled_tasks"),  # For test tasks and other scheduled tasks
    ),
    # Worker configuration
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,
    # === DATABASE-DRIVEN SCHEDULER CONFIGURATION ===
    # Use django-celery-beat for database-driven scheduling
    beat_scheduler="django_celery_beat.schedulers:DatabaseScheduler",
    beat_max_loop_interval=30,  # Check database every 30 seconds
    # Static schedules (for system tasks that don't need dynamic management)
    beat_schedule={
        "cleanup-old-executions": {
            "task": "cleanup_old_executions",
            "schedule": crontab(hour=2, minute=0),  # Daily at 2:00 AM UTC
            "args": (90,),  # Keep 90 days of execution records
            "options": {"queue": "default"},
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(
    [
        "ada_backend.tasks.workflow_tasks",  # Workflow execution tasks
        "ada_backend.tasks.test_tasks",  # Test tasks
    ]
)

if __name__ == "__main__":
    celery_app.start()
