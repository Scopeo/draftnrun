"""add secret to variable type enum

Revision ID: d5f1a8c3e927
Revises: c8e2f4a6b710
Create Date: 2026-02-10 00:02:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5f1a8c3e927"
down_revision: Union[str, None] = "c8e2f4a6b710"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE variable_type ADD VALUE IF NOT EXISTS 'secret'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    # A full enum recreation would be needed to reverse this.
    pass
