"""Add_Updating_existing_source_ingestion_task_status

Revision ID: f7e0c94411dd
Revises: 80118747a315
Create Date: 2025-07-17 17:48:51.968117

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f7e0c94411dd"
down_revision: Union[str, None] = "80118747a315"
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
