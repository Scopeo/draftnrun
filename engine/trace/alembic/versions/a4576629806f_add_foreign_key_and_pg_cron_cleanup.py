"""add_foreign_key_and_pg_cron_cleanup

Revision ID: a4576629806f
Revises: 55bf7791d9dd
Create Date: 2025-10-21 13:08:54.099132

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a4576629806f"
down_revision: Union[str, None] = "55bf7791d9dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clean up orphaned span_messages records
    op.execute(
        """
        DELETE FROM span_messages
        WHERE span_id NOT IN (SELECT span_id FROM spans)
    """
    )

    op.create_foreign_key(None, "span_messages", "spans", ["span_id"], ["span_id"], ondelete="CASCADE")

    op.execute("DROP INDEX IF EXISTS ix_spans_call_type;")
    op.execute("DROP INDEX IF EXISTS ix_spans_environment;")

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_cron;")

    # Clean up old spans daily at 2 AM UTC
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'cleanup-old-spans') THEN
                PERFORM cron.schedule(
                    'cleanup-old-spans',
                    '0 2 * * *',  -- 2 AM UTC daily
                    $cleanup$
                    DELETE FROM span_messages
                    WHERE span_id IN (
                        SELECT s.span_id FROM spans s
                        WHERE s.start_time < NOW() - INTERVAL '90 days'
                    );
                    $cleanup$
                );
            END IF;
        END $$;
    """
    )


def downgrade() -> None:
    # Remove the cleanup job
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'cleanup-old-spans') THEN
                PERFORM cron.unschedule('cleanup-old-spans');
            END IF;
        END $$;
    """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_spans_environment ON spans (environment);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_spans_call_type ON spans (call_type);")
    op.drop_constraint("span_messages_span_id_fkey", "span_messages", type_="foreignkey", if_exists=True)
