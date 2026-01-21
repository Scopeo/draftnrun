"""remove_message_and_artifact_from_cron_results

Revision ID: 9e46c1d3afb3
Revises: 7aa8f5d4fe12
Create Date: 2026-01-20 17:53:14.492197

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e46c1d3afb3"
down_revision: Union[str, None] = "7aa8f5d4fe12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove 'message' and 'artifacts' fields from cron_runs results
    op.execute(
        """
        UPDATE scheduler.cron_runs
        SET result = result - 'message' - 'artifacts'
        WHERE result ? 'message' OR result ? 'artifacts';
        """
    )

    # Remove 'message' field from workflows_triggered array in endpoint_polling results
    op.execute(
        """
        UPDATE scheduler.cron_runs
        SET result = jsonb_set(
            result,
            '{workflows_triggered}',
            COALESCE((
                SELECT jsonb_agg(elem - 'message')
                FROM jsonb_array_elements(result->'workflows_triggered') elem
            ), '[]'::jsonb),
            true
        )
        WHERE result ? 'workflows_triggered'
        AND result->'workflows_triggered' IS NOT NULL
        AND jsonb_typeof(result->'workflows_triggered') = 'array';
        """
    )


def downgrade() -> None:
    # Note: We cannot restore the removed data in downgrade
    # as it has been permanently deleted. This is a data cleanup migration.
    pass
