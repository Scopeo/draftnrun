#!/usr/bin/env python3
"""
Setup script to create django-celery-beat tables directly in custom schema.
This script creates the django_beat_cron_scheduler schema and creates all
necessary tables for django-celery-beat without running Django migrations.
"""

import sys
import logging
from ada_backend.utils.database_utils import get_postgres_connection

# Setup logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)


def create_django_beat_tables():
    """Create django-celery-beat tables directly in custom schema"""

    LOGGER.info("Creating django-celery-beat tables in custom schema...")

    try:
        with get_postgres_connection() as (conn, cursor):
            # Create the custom schema
            LOGGER.info("Creating django_beat_cron_scheduler schema...")
            cursor.execute("CREATE SCHEMA IF NOT EXISTS django_beat_cron_scheduler")
            LOGGER.info("Schema created successfully")

            # Create django_celery_beat_crontabschedule table
            LOGGER.info("Creating crontabschedule table...")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS django_beat_cron_scheduler.django_celery_beat_crontabschedule (
                    id SERIAL PRIMARY KEY,
                    minute VARCHAR(240) NOT NULL DEFAULT '*',
                    hour VARCHAR(96) NOT NULL DEFAULT '*',
                    day_of_week VARCHAR(64) NOT NULL DEFAULT '*',
                    day_of_month VARCHAR(124) NOT NULL DEFAULT '*',
                    month_of_year VARCHAR(64) NOT NULL DEFAULT '*',
                    timezone VARCHAR(63) NOT NULL DEFAULT 'UTC'
                )
            """
            )

            # Create django_celery_beat_intervalschedule table
            LOGGER.info("Creating intervalschedule table...")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS django_beat_cron_scheduler.django_celery_beat_intervalschedule (
                    id SERIAL PRIMARY KEY,
                    every INTEGER NOT NULL,
                    period VARCHAR(24) NOT NULL
                )
            """
            )

            # Create django_celery_beat_solarschedule table
            LOGGER.info("Creating solarschedule table...")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS django_beat_cron_scheduler.django_celery_beat_solarschedule (
                    id SERIAL PRIMARY KEY,
                    event VARCHAR(16) NOT NULL,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL
                )
            """
            )

            # Create django_celery_beat_clockedschedule table
            LOGGER.info("Creating clockedschedule table...")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS django_beat_cron_scheduler.django_celery_beat_clockedschedule (
                    id SERIAL PRIMARY KEY,
                    clocked_time TIMESTAMP WITH TIME ZONE NOT NULL
                )
            """
            )

            # Create django_celery_beat_periodictask table
            LOGGER.info("Creating periodictask table...")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS django_beat_cron_scheduler.django_celery_beat_periodictask (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL UNIQUE,
                    task VARCHAR(200) NOT NULL,
                    crontab_id INTEGER REFERENCES django_beat_cron_scheduler.django_celery_beat_crontabschedule(id) ON DELETE SET NULL,
                    interval_id INTEGER REFERENCES django_beat_cron_scheduler.django_celery_beat_intervalschedule(id) ON DELETE SET NULL,
                    solar_id INTEGER REFERENCES django_beat_cron_scheduler.django_celery_beat_solarschedule(id) ON DELETE SET NULL,
                    clocked_id INTEGER REFERENCES django_beat_cron_scheduler.django_celery_beat_clockedschedule(id) ON DELETE SET NULL,
                    args TEXT NOT NULL DEFAULT '[]',
                    kwargs TEXT NOT NULL DEFAULT '{}',
                    queue VARCHAR(200),
                    exchange VARCHAR(200),
                    routing_key VARCHAR(200),
                    headers TEXT NOT NULL DEFAULT '{}',
                    expires TIMESTAMP WITH TIME ZONE,
                    expire_seconds INTEGER,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    last_run_at TIMESTAMP WITH TIME ZONE,
                    total_run_count INTEGER NOT NULL DEFAULT 0,
                    date_changed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    description TEXT NOT NULL DEFAULT '',
                    priority INTEGER,
                    one_off BOOLEAN NOT NULL DEFAULT FALSE,
                    start_time TIMESTAMP WITH TIME ZONE,
                    scheduled_workflow_uuid UUID
                )
            """
            )

            # Create django_celery_beat_periodictasks table
            LOGGER.info("Creating periodictasks table...")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS django_beat_cron_scheduler.django_celery_beat_periodictasks (
                    ident INTEGER PRIMARY KEY,
                    last_update TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """
            )

            # Insert initial record for change tracking
            LOGGER.info("Inserting initial periodictasks record...")
            cursor.execute(
                """
                INSERT INTO django_beat_cron_scheduler.django_celery_beat_periodictasks (ident, last_update)
                VALUES (1, NOW())
                ON CONFLICT (ident) DO NOTHING
            """
            )

            # Create indexes for better performance
            LOGGER.info("Creating indexes...")
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scheduled_workflow_uuid
                ON django_beat_cron_scheduler.django_celery_beat_periodictask(scheduled_workflow_uuid)
            """
            )

            LOGGER.info("All django-celery-beat tables created successfully!")

            # Verify table creation
            LOGGER.info("Verifying table creation...")
            cursor.execute(
                """
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'django_beat_cron_scheduler'
                ORDER BY table_name
            """
            )
            tables = cursor.fetchall()

            if tables:
                LOGGER.info("Tables created in django_beat_cron_scheduler schema:")
                for table in tables:
                    LOGGER.info(f"  - {table[0]}")
            else:
                LOGGER.warning("No tables found in django_beat_cron_scheduler schema")

            return True

    except Exception as e:
        LOGGER.error(f"Failed to create django-celery-beat tables: {str(e)}")
        return False


def main():
    """Main function"""
    LOGGER.info("Starting django-celery-beat schema setup...")

    success = create_django_beat_tables()

    if success:
        LOGGER.info("✅ Django-celery-beat schema setup completed successfully!")
        return 0
    else:
        LOGGER.error("❌ Django-celery-beat schema setup failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
