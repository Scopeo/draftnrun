"""add website type in sources

Revision ID: 1d0c97757e4d
Revises: b0ba5107a7e3
Create Date: 2025-01-27 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1d0c97757e4d"
down_revision: Union[str, None] = "b0ba5107a7e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'website'")


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM ingestion_tasks
        WHERE source_id IN (
            SELECT id FROM data_sources
            WHERE type = 'website'
        )
    """
    )
    op.execute(
        """
        DELETE FROM data_sources
        WHERE type = 'website'
    """
    )
