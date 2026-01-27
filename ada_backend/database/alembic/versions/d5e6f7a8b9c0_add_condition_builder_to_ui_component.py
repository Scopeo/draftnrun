"""add condition builder to ui component enum

Revision ID: d5e6f7a8b9c0
Revises: 9e46c1d3afb3
Create Date: 2026-01-26 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "9e46c1d3afb3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'ConditionBuilder' value to the ui_component enum
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'ConditionBuilder'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The 'ConditionBuilder' value will remain in the enum type even after downgrade.
    # This is harmless and won't affect the application.
    pass
