"""add queued to cron_status

Revision ID: a9b0c1d2e3f4
Revises: 4071a252013a
Create Date: 2026-03-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "4071a252013a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL requires enum value additions to be committed outside Alembic's transaction.
    op.execute("ALTER TYPE scheduler.cron_status ADD VALUE IF NOT EXISTS 'queued'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    # Rows with status='queued' should be migrated before downgrading.
    pass
