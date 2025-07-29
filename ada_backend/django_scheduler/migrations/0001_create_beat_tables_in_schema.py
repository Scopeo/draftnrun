from django.db import migrations


class Migration(migrations.Migration):
    dependencies = []
    operations = [
        # Create all django-celery-beat tables in public schema using RunSQL
        migrations.RunSQL(
            """
            -- 1. Create django_celery_beat_intervalschedule table (no dependencies)
            CREATE TABLE IF NOT EXISTS django_celery_beat_intervalschedule (
                id SERIAL PRIMARY KEY,
                every INTEGER NOT NULL,
                period VARCHAR(24) NOT NULL
            );

            -- 2. Create django_celery_beat_crontabschedule table (no dependencies)
            CREATE TABLE IF NOT EXISTS django_celery_beat_crontabschedule (
                id SERIAL PRIMARY KEY,
                minute VARCHAR(240) NOT NULL DEFAULT '*',
                hour VARCHAR(96) NOT NULL DEFAULT '*',
                day_of_week VARCHAR(64) NOT NULL DEFAULT '*',
                day_of_month VARCHAR(124) NOT NULL DEFAULT '*',
                month_of_year VARCHAR(64) NOT NULL DEFAULT '*',
                timezone VARCHAR(63) NOT NULL DEFAULT 'UTC'
            );

            -- 3. Create django_celery_beat_solarschedule table (no dependencies)
            CREATE TABLE IF NOT EXISTS django_celery_beat_solarschedule (
                id SERIAL PRIMARY KEY,
                event VARCHAR(16) NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL
            );

            -- 4. Create django_celery_beat_clockedschedule table (no dependencies)
            CREATE TABLE IF NOT EXISTS django_celery_beat_clockedschedule (
                id SERIAL PRIMARY KEY,
                clocked_time TIMESTAMP WITH TIME ZONE NOT NULL
            );

            -- 5. Create django_celery_beat_periodictask table (depends on all schedule tables)
            CREATE TABLE IF NOT EXISTS django_celery_beat_periodictask (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL UNIQUE,
                task VARCHAR(200) NOT NULL,
                crontab_id INTEGER REFERENCES django_celery_beat_crontabschedule(id) ON DELETE SET NULL,
                interval_id INTEGER REFERENCES django_celery_beat_intervalschedule(id) ON DELETE SET NULL,
                solar_id INTEGER REFERENCES django_celery_beat_solarschedule(id) ON DELETE SET NULL,
                clocked_id INTEGER REFERENCES django_celery_beat_clockedschedule(id) ON DELETE SET NULL,
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

            -- 6. Create django_celery_beat_periodictasks table (singleton tracking model)
            CREATE TABLE IF NOT EXISTS django_celery_beat_periodictasks (
                ident INTEGER PRIMARY KEY,
                last_update TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            -- Create indexes for better performance
            CREATE INDEX IF NOT EXISTS idx_periodictask_name ON django_celery_beat_periodictask(name);
            CREATE INDEX IF NOT EXISTS idx_periodictask_task ON django_celery_beat_periodictask(task);
            CREATE INDEX IF NOT EXISTS idx_periodictask_enabled ON django_celery_beat_periodictask(enabled);
            CREATE INDEX IF NOT EXISTS idx_periodictask_crontab_id ON django_celery_beat_periodictask(crontab_id);
            CREATE INDEX IF NOT EXISTS idx_periodictask_interval_id ON django_celery_beat_periodictask(interval_id);
            CREATE INDEX IF NOT EXISTS idx_periodictask_solar_id ON django_celery_beat_periodictask(solar_id);
            CREATE INDEX IF NOT EXISTS idx_periodictask_clocked_id ON django_celery_beat_periodictask(clocked_id);
            """,
            """
            -- Drop tables in reverse dependency order
            DROP TABLE IF EXISTS django_celery_beat_periodictasks CASCADE;
            DROP TABLE IF EXISTS django_celery_beat_periodictask CASCADE;
            DROP TABLE IF EXISTS django_celery_beat_clockedschedule CASCADE;
            DROP TABLE IF EXISTS django_celery_beat_solarschedule CASCADE;
            DROP TABLE IF EXISTS django_celery_beat_crontabschedule CASCADE;
            DROP TABLE IF EXISTS django_celery_beat_intervalschedule CASCADE;
            """,
        ),
    ]
