"""add_updating_existing_source_ingestion_status

Revision ID: 645a4a3bd59c
Revises: 0d0db05d4dac
Create Date: 2025-07-29 14:16:35.166906

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "645a4a3bd59c"
down_revision: Union[str, None] = "0d0db05d4dac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new enum value to the task_status enum
    op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'updating_existing_source'")


def downgrade() -> None:
    # Remove any ingestion tasks that use the new status
    op.execute(
        """
        DELETE FROM ingestion_tasks
        WHERE status = 'updating_existing_source'
        """
    )
