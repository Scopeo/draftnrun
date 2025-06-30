"""add_remote_local_folder_in_ingestion

Revision ID: 6f0df1ce9f2c
Revises: 80118747a315
Create Date: 2025-06-27 17:14:28.114990

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f0df1ce9f2c"
down_revision: Union[str, None] = "80118747a315"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new value to the enum
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'dev_local'")


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM ingestion_tasks
        WHERE source_id IN (
            SELECT id FROM data_sources
            WHERE type = 'dev_local'
        )
    """
    )
    op.execute(
        """
        DELETE FROM data_sources
        WHERE type = 'dev_local'
    """
    )
