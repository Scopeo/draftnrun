"""
Custom Django models for django-celery-beat tables in public schema.
These models extend the standard django-celery-beat models with custom functionality.
"""

from django.db import models


class CrontabSchedule(models.Model):
    """Custom model for django_celery_beat_crontabschedule table in public schema."""

    class Meta:
        db_table = "django_celery_beat_crontabschedule"
        managed = False  # Don't let Django manage this table

    id = models.AutoField(primary_key=True)
    minute = models.CharField(max_length=240, default="*")
    hour = models.CharField(max_length=96, default="*")
    day_of_week = models.CharField(max_length=64, default="*")
    day_of_month = models.CharField(max_length=124, default="*")
    month_of_year = models.CharField(max_length=64, default="*")
    timezone = models.CharField(max_length=63, default="UTC")


class IntervalSchedule(models.Model):
    """Custom model for django_celery_beat_intervalschedule table in public schema."""

    class Meta:
        db_table = "django_celery_beat_intervalschedule"
        managed = False  # Don't let Django manage this table

    id = models.AutoField(primary_key=True)
    every = models.IntegerField()
    period = models.CharField(max_length=24)


class SolarSchedule(models.Model):
    """Custom model for django_celery_beat_solarschedule table in public schema."""

    class Meta:
        db_table = "django_celery_beat_solarschedule"
        managed = False  # Don't let Django manage this table

    id = models.AutoField(primary_key=True)
    event = models.CharField(max_length=16)
    latitude = models.FloatField()
    longitude = models.FloatField()


class ClockedSchedule(models.Model):
    """Custom model for django_celery_beat_clockedschedule table in public schema."""

    class Meta:
        db_table = "django_celery_beat_clockedschedule"
        managed = False  # Don't let Django manage this table

    id = models.AutoField(primary_key=True)
    clocked_time = models.DateTimeField()


class PeriodicTask(models.Model):
    """Custom model for django_celery_beat_periodictask table in public schema."""

    class Meta:
        db_table = "django_celery_beat_periodictask"
        managed = False  # Don't let Django manage this table

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200, unique=True)
    task = models.CharField(max_length=200)
    crontab = models.ForeignKey(CrontabSchedule, on_delete=models.SET_NULL, null=True, blank=True)
    interval = models.ForeignKey(IntervalSchedule, on_delete=models.SET_NULL, null=True, blank=True)
    solar = models.ForeignKey(SolarSchedule, on_delete=models.SET_NULL, null=True, blank=True)
    clocked = models.ForeignKey(ClockedSchedule, on_delete=models.SET_NULL, null=True, blank=True)
    args = models.TextField(default="[]")
    kwargs = models.TextField(default="{}")
    queue = models.CharField(max_length=200, null=True, blank=True)
    exchange = models.CharField(max_length=200, null=True, blank=True)
    routing_key = models.CharField(max_length=200, null=True, blank=True)
    headers = models.TextField(default="{}")
    expires = models.DateTimeField(null=True, blank=True)
    expire_seconds = models.IntegerField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    total_run_count = models.IntegerField(default=0)
    date_changed = models.DateTimeField(auto_now=True)
    description = models.TextField(default="")
    priority = models.IntegerField(null=True, blank=True)
    one_off = models.BooleanField(default=False)
    start_time = models.DateTimeField(null=True, blank=True)


class PeriodicTasks(models.Model):
    """Custom model for django_celery_beat_periodictasks table in public schema."""

    class Meta:
        db_table = "django_celery_beat_periodictasks"
        managed = False  # Don't let Django manage this table

    ident = models.IntegerField(primary_key=True)
    last_update = models.DateTimeField(auto_now=True)
