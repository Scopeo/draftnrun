from django.db import migrations


class Migration(migrations.Migration):
    dependencies = []
    operations = [
        # Create the schema first
        migrations.RunSQL(
            "CREATE SCHEMA IF NOT EXISTS scheduled_workflows;", "DROP SCHEMA IF EXISTS scheduled_workflows CASCADE;"
        ),
        # Override django_celery_beat.0001_initial to create tables in schema
        migrations.RunSQL(
            """
            -- Create django_celery_beat_crontabschedule in schema
            CREATE TABLE scheduled_workflows.django_celery_beat_crontabschedule (
                id SERIAL PRIMARY KEY,
                minute VARCHAR(240) NOT NULL DEFAULT '*',
                hour VARCHAR(96) NOT NULL DEFAULT '*',
                day_of_week VARCHAR(64) NOT NULL DEFAULT '*',
                day_of_month VARCHAR(124) NOT NULL DEFAULT '*',
                month_of_year VARCHAR(64) NOT NULL DEFAULT '*',
                timezone VARCHAR(63) NOT NULL DEFAULT 'UTC'
            );
            -- Create django_celery_beat_periodictasks in schema
            CREATE TABLE scheduled_workflows.django_celery_beat_periodictasks (
                ident INTEGER PRIMARY KEY,
                last_update TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            -- Create django_celery_beat_periodictask in schema
            CREATE TABLE scheduled_workflows.django_celery_beat_periodictask (
                id SERIAL PRIMARY KEY,
                name VARCHAR(200) NOT NULL UNIQUE,
                task VARCHAR(200) NOT NULL,
                crontab_id INTEGER REFERENCES scheduled_workflows.django_celery_beat_crontabschedule(id),
                args TEXT NOT NULL DEFAULT '[]',
                kwargs TEXT NOT NULL DEFAULT '{}',
                queue VARCHAR(200),
                exchange VARCHAR(200),
                routing_key VARCHAR(200),
                expires TIMESTAMP WITH TIME ZONE,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                last_run_at TIMESTAMP WITH TIME ZONE,
                total_run_count INTEGER NOT NULL DEFAULT 0,
                date_changed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                description TEXT NOT NULL DEFAULT ''
            );
            -- Create indexes
            CREATE INDEX idx_periodictask_name ON scheduled_workflows.django_celery_beat_periodictask(name);
            CREATE INDEX idx_periodictask_task ON scheduled_workflows.django_celery_beat_periodictask(task);
            CREATE INDEX idx_periodictask_enabled ON scheduled_workflows.django_celery_beat_periodictask(enabled);
            """,
            """
            -- Drop tables in reverse order
            DROP TABLE IF EXISTS scheduled_workflows.django_celery_beat_periodictask CASCADE;
            DROP TABLE IF EXISTS scheduled_workflows.django_celery_beat_periodictasks CASCADE;
            DROP TABLE IF EXISTS scheduled_workflows.django_celery_beat_crontabschedule CASCADE;
            """,
        ),
        # Mark django_celery_beat migrations as applied to prevent conflicts
        migrations.RunSQL(
            """
            -- Insert migration records to mark django_celery_beat migrations as applied
            INSERT INTO django_migrations (app, name, applied) VALUES
            ('django_celery_beat', '0001_initial', NOW()),
            ('django_celery_beat', '0002_auto_20161118_0346', NOW()),
            ('django_celery_beat', '0003_auto_20161209_0049', NOW()),
            ('django_celery_beat', '0004_auto_20170221_0000', NOW()),
            ('django_celery_beat', '0005_add_solarschedule_events_choices', NOW()),
            ('django_celery_beat', '0006_auto_20180322_0932', NOW()),
            ('django_celery_beat', '0007_auto_20180521_0826', NOW()),
            ('django_celery_beat', '0008_auto_20180914_1922', NOW()),
            ('django_celery_beat', '0006_auto_20180210_1226', NOW()),
            ('django_celery_beat', '0006_periodictask_priority', NOW()),
            ('django_celery_beat', '0009_periodictask_headers', NOW()),
            ('django_celery_beat', '0010_auto_20190429_0326', NOW()),
            ('django_celery_beat', '0011_auto_20190508_0153', NOW()),
            ('django_celery_beat', '0012_periodictask_expire_seconds', NOW()),
            ('django_celery_beat', '0013_auto_20200609_0727', NOW()),
            ('django_celery_beat', '0014_remove_clockedschedule_enabled', NOW()),
            ('django_celery_beat', '0015_edit_solarschedule_events_choices', NOW()),
            ('django_celery_beat', '0016_alter_crontabschedule_timezone', NOW()),
            ('django_celery_beat', '0017_alter_crontabschedule_month_of_year', NOW()),
            ('django_celery_beat', '0018_improve_crontab_helptext', NOW()),
            ('django_celery_beat', '0019_alter_periodictasks_options', NOW())
            ON CONFLICT (app, name) DO NOTHING;
            """,
            """
            -- Remove migration records if needed
            DELETE FROM django_migrations WHERE app = 'django_celery_beat';
            """,
        ),
    ]
