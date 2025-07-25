from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create django-celery-beat tables in scheduled_workflows schema"

    def handle(self, *args, **options):
        self.stdout.write("Creating django-celery-beat tables in scheduled_workflows schema...")

        with connection.cursor() as cursor:
            # Create schema
            cursor.execute("CREATE SCHEMA IF NOT EXISTS scheduled_workflows;")

            # 1. Create django_celery_beat_intervalschedule table (no dependencies)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_workflows.django_celery_beat_intervalschedule (
                    id SERIAL PRIMARY KEY,
                    every INTEGER NOT NULL,
                    period VARCHAR(24) NOT NULL
                );
            """
            )

            # 2. Create django_celery_beat_crontabschedule table (no dependencies)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_workflows.django_celery_beat_crontabschedule (
                    id SERIAL PRIMARY KEY,
                    minute VARCHAR(240) NOT NULL DEFAULT '*',
                    hour VARCHAR(96) NOT NULL DEFAULT '*',
                    day_of_week VARCHAR(64) NOT NULL DEFAULT '*',
                    day_of_month VARCHAR(124) NOT NULL DEFAULT '*',
                    month_of_year VARCHAR(64) NOT NULL DEFAULT '*',
                    timezone VARCHAR(63) NOT NULL DEFAULT 'UTC'
                );
            """
            )

            # 3. Create django_celery_beat_solarschedule table (no dependencies)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_workflows.django_celery_beat_solarschedule (
                    id SERIAL PRIMARY KEY,
                    event VARCHAR(16) NOT NULL,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL
                );
            """
            )

            # 4. Create django_celery_beat_clockedschedule table (no dependencies)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_workflows.django_celery_beat_clockedschedule (
                    id SERIAL PRIMARY KEY,
                    clocked_time TIMESTAMP WITH TIME ZONE NOT NULL
                );
            """
            )

            # 5. Create django_celery_beat_periodictask table (depends on all schedule tables)
            periodic_task_sql = """
                CREATE TABLE IF NOT EXISTS scheduled_workflows.django_celery_beat_periodictask (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL UNIQUE,
                    task VARCHAR(200) NOT NULL,
                    crontab_id INTEGER REFERENCES scheduled_workflows.django_celery_beat_crontabschedule(id)
                        ON DELETE SET NULL,
                    interval_id INTEGER REFERENCES scheduled_workflows.django_celery_beat_intervalschedule(id)
                        ON DELETE SET NULL,
                    solar_id INTEGER REFERENCES scheduled_workflows.django_celery_beat_solarschedule(id)
                        ON DELETE SET NULL,
                    clocked_id INTEGER REFERENCES scheduled_workflows.django_celery_beat_clockedschedule(id)
                        ON DELETE SET NULL,
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
                    start_time TIMESTAMP WITH TIME ZONE
                );
            """
            cursor.execute(periodic_task_sql)

            # 6. Create django_celery_beat_periodictasks table (singleton tracking model)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_workflows.django_celery_beat_periodictasks (
                    ident INTEGER PRIMARY KEY,
                    last_update TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """
            )

            # Create indexes for better performance
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_periodictask_name
                ON scheduled_workflows.django_celery_beat_periodictask(name);
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_periodictask_task
                ON scheduled_workflows.django_celery_beat_periodictask(task);
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_periodictask_enabled
                ON scheduled_workflows.django_celery_beat_periodictask(enabled);
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_periodictask_crontab_id
                ON scheduled_workflows.django_celery_beat_periodictask(crontab_id);
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_periodictask_interval_id
                ON scheduled_workflows.django_celery_beat_periodictask(interval_id);
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_periodictask_solar_id
                ON scheduled_workflows.django_celery_beat_periodictask(solar_id);
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_periodictask_clocked_id
                ON scheduled_workflows.django_celery_beat_periodictask(clocked_id);
            """
            )

            # Check if django_migrations table exists before trying to insert
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'django_migrations'
                );
            """
            )
            migrations_table_exists = cursor.fetchone()[0]

            if migrations_table_exists:
                # Mark migrations as applied to prevent conflicts (without ON CONFLICT)
                migrations_to_insert = [
                    ("django_celery_beat", "0001_initial"),
                    ("django_celery_beat", "0002_auto_20161118_0346"),
                    ("django_celery_beat", "0003_auto_20161209_0049"),
                    ("django_celery_beat", "0004_auto_20170221_0000"),
                    ("django_celery_beat", "0005_add_solarschedule_events_choices"),
                    ("django_celery_beat", "0006_auto_20180322_0932"),
                    ("django_celery_beat", "0007_auto_20180521_0826"),
                    ("django_celery_beat", "0008_auto_20180914_1922"),
                    ("django_celery_beat", "0006_auto_20180210_1226"),
                    ("django_celery_beat", "0006_periodictask_priority"),
                    ("django_celery_beat", "0009_periodictask_headers"),
                    ("django_celery_beat", "0010_auto_20190429_0326"),
                    ("django_celery_beat", "0011_auto_20190508_0153"),
                    ("django_celery_beat", "0012_periodictask_expire_seconds"),
                    ("django_celery_beat", "0013_auto_20200609_0727"),
                    ("django_celery_beat", "0014_remove_clockedschedule_enabled"),
                    ("django_celery_beat", "0015_edit_solarschedule_events_choices"),
                    ("django_celery_beat", "0016_alter_crontabschedule_timezone"),
                    ("django_celery_beat", "0017_alter_crontabschedule_month_of_year"),
                    ("django_celery_beat", "0018_improve_crontab_helptext"),
                    ("django_celery_beat", "0019_alter_periodictasks_options"),
                ]

                for app, name in migrations_to_insert:
                    try:
                        cursor.execute(
                            """
                            INSERT INTO django_migrations (app, name, applied)
                            VALUES (%s, %s, NOW())
                        """,
                            [app, name],
                        )
                    except Exception:
                        # Migration already exists, skip
                        pass

                self.stdout.write("Migration records marked as applied.")
            else:
                self.stdout.write("django_migrations table does not exist, skipping migration records.")

        self.stdout.write(
            self.style.SUCCESS("Successfully created django-celery-beat tables in scheduled_workflows schema")
        )
