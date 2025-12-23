"""add_result_metadata_to_ingestion_tasks

Revision ID: abc123def456
Revises: cfe3267603c1
Create Date: 2025-12-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "abc123def456"
down_revision: Union[str, None] = "cfe3267603c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add error_message JSONB column to ingestion_tasks table."""
    op.add_column(
        "ingestion_tasks",
        sa.Column("result_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Remove error_message column from ingestion_tasks table."""
    op.drop_column("ingestion_tasks", "result_metadata")
