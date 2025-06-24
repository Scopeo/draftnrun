"""add_remote_local_folder_in_ingestion_code

Revision ID: 7d483c5eaf1e
Revises: 2301736f9201
Create Date: 2025-06-24 18:02:04.028029

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d483c5eaf1e"
down_revision: Union[str, None] = "2301736f9201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new value to the enum
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'remote_local'")


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM ingestion_tasks
        WHERE source_id IN (
            SELECT id FROM data_sources
            WHERE type = 'remote_local'
        )
    """
    )
    op.execute(
        """
        DELETE FROM data_sources
        WHERE type = 'remote_local'
    """
    )
