"""add_foreign_key_and_pg_cron_cleanup

Revision ID: a4576629806f
Revises: 8729faf18d1c
Create Date: 2025-10-21 13:08:54.099132

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import create_engine, text


# revision identifiers, used by Alembic.
revision: str = "a4576629806f"
down_revision: Union[str, None] = "8729faf18d1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _run_in_postgres(sql: str):
    bind = op.get_bind()
    original_url = bind.engine.url
    postgres_url = original_url.set(database="postgres")
    connect_args = getattr(bind.engine, "connect_args", {}) or {}
    postgres_engine = create_engine(postgres_url, connect_args=connect_args)
    with postgres_engine.begin() as conn:
        return conn.execute(text(sql))


def upgrade() -> None:
    # Clean up orphaned span_messages records
    op.execute(
        """
        DELETE FROM traces.span_messages
        WHERE span_id NOT IN (SELECT span_id FROM traces.spans)
    """
    )

    # Add foreign key constraint to span_messages table
    op.execute(
        """
        ALTER TABLE traces.span_messages
        ADD CONSTRAINT span_messages_span_id_fkey
        FOREIGN KEY (span_id) REFERENCES traces.spans(span_id) ON DELETE CASCADE
    """
    )

    bind = op.get_bind()
    current_db = bind.engine.url.database

    # Validate pg_cron is installed and accessible in the postgres DB
    has_cron_job_table = _run_in_postgres(
        """
        SELECT to_regclass('cron.job') IS NOT NULL
        """
    ).scalar()
    if not has_cron_job_table:
        raise RuntimeError(
            "pg_cron is not installed/configured. "
            "Install extension in the 'postgres' database and ensure shared_preload_libraries includes pg_cron."
        )

    has_schedule_in_db = _run_in_postgres(
        """
        SELECT EXISTS (
          SELECT 1
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
          WHERE n.nspname = 'cron' AND p.proname = 'schedule_in_database'
        )
        """
    ).scalar()

    if not has_schedule_in_db:
        raise RuntimeError("pg_cron.schedule_in_database() is required")

    _run_in_postgres(
        f"""
        SELECT cron.schedule_in_database(
            'cleanup-old-spans',
            '0 2 * * *',
            $q$
            DELETE FROM traces.span_messages
            WHERE span_id IN (
                SELECT s.span_id FROM traces.spans s
                WHERE s.start_time < NOW() - INTERVAL '90 days'
            );
            $q$,
            '{current_db}'
        )
        WHERE NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'cleanup-old-spans');
        """
    )


def downgrade() -> None:
    _run_in_postgres(
        """
        DO $$
        DECLARE
            jid bigint;
        BEGIN
            SELECT jobid INTO jid FROM cron.job WHERE jobname = 'cleanup-old-spans';
            IF jid IS NOT NULL THEN
                PERFORM cron.unschedule(jid);
            END IF;
        END $$;
        """
    )

    op.execute("ALTER TABLE traces.span_messages DROP CONSTRAINT IF EXISTS span_messages_span_id_fkey")
