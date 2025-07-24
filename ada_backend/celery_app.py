"""
Celery app configuration for ada_backend.
Handles scheduling and background task execution.
Uses django-celery-beat for persistent, database-driven scheduling.
"""

import logging
import os
from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from settings import settings

# Configure Django settings for django-celery-beat
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ada_backend.django_settings')

# Minimal Django configuration for django-celery-beat
import django
from django.conf import settings as django_settings

if not django_settings.configured:
    try:
        django_settings.configure(
            DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.postgresql',
                    'NAME': settings.ADA_DB_NAME,
                    'USER': settings.ADA_DB_USER,
                    'PASSWORD': settings.ADA_DB_PASSWORD,
                    'HOST': settings.ADA_DB_HOST,
                    'PORT': settings.ADA_DB_PORT,
                }
            },
            INSTALLED_APPS=[
                'django.contrib.auth',
                'django.contrib.contenttypes',
                'django.contrib.sessions',
                'django_celery_beat',
            ],
            USE_TZ=True,
            TIME_ZONE='UTC',
            USE_DEPRECATED_PYTZ=False,
            SECRET_KEY='django-celery-beat-minimal-config',
            DEBUG=False,
            MIDDLEWARE=[
                'django.middleware.security.SecurityMiddleware',
                'django.contrib.sessions.middleware.SessionMiddleware',
                'django.middleware.common.CommonMiddleware',
                'django.middleware.csrf.CsrfViewMiddleware',
                'django.contrib.auth.middleware.AuthenticationMiddleware',
            ],
            CACHES={
                'default': {
                    'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
                    'LOCATION': 'django_cache',
                }
            },
            # ROOT_URLCONF='ada_backend.django_settings',  # Removed - not needed
            # WSGI_APPLICATION='ada_backend.django_settings.application',  # Removed - not needed
            TEMPLATES=[
                {
                    'BACKEND': 'django.template.backends.django.DjangoTemplates',
                    'DIRS': [],
                    'APP_DIRS': True,
                    'OPTIONS': {
                        'context_processors': [
                            'django.template.context_processors.debug',
                            'django.template.context_processors.request',
                            'django.contrib.auth.context_processors.auth',
                            'django.contrib.messages.context_processors.messages',
                        ],
                    },
                },
            ],
        )
        django.setup()
        logging.getLogger(__name__).info("Django configured successfully for django-celery-beat")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to configure Django: {e}")
        raise

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
    
    # Task routing - only execution tasks use Redis
    task_routes={
        "ada_backend.tasks.workflow_tasks.*": {"queue": "scheduled_workflows"},
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
    
    # === DATABASE-DRIVEN SCHEDULER CONFIGURATION ===
    # Use django-celery-beat for database-driven scheduling
    beat_scheduler='django_celery_beat.schedulers:DatabaseScheduler',
    beat_max_loop_interval=30,  # Check database every 30 seconds
    
    # Static schedules (for system tasks that don't need dynamic management)
    beat_schedule={
        'cleanup-old-executions': {
            'task': 'cleanup_old_executions',
            'schedule': crontab(hour=2, minute=0),  # Daily at 2:00 AM UTC
            'args': (90,),  # Keep 90 days of execution records
            'options': {'queue': 'default'}
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(
    [
        "ada_backend.tasks.workflow_tasks",  # Only workflow execution tasks
    ]
)

if __name__ == "__main__":
    celery_app.start()
