"""
Django models for django-celery-beat integration.
This file provides access to django-celery-beat models.
"""

# Import the models directly from django-celery-beat
from django_celery_beat.models import PeriodicTask, CrontabSchedule, PeriodicTasks

# Re-export them for convenience
__all__ = ["PeriodicTask", "CrontabSchedule", "PeriodicTasks"]
