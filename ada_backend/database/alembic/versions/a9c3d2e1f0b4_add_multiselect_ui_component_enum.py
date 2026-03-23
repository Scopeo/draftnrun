"""add multiselect ui component enum value

Revision ID: a9c3d2e1f0b4
Revises: b1c2d3e4f5a7
Create Date: 2026-03-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c3d2e1f0b4"
down_revision: Union[str, None] = "b1c2d3e4f5a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new value to ui_component enum
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'MultiSelect'")


def downgrade() -> None:
    pass
