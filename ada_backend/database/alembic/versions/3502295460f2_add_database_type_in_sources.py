"""add database type in sources

Revision ID: 3502295460f2
Revises: 3ab342cef192
Create Date: 2025-06-06 18:46:02.996516

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3502295460f2"
down_revision: Union[str, None] = "3ab342cef192"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'database'")


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM ingestion_tasks
        WHERE source_id IN (
            SELECT id FROM data_sources
            WHERE type = 'database'
        )
    """
    )
    op.execute(
        """
        DELETE FROM data_sources
        WHERE type = 'database'
    """
    )
