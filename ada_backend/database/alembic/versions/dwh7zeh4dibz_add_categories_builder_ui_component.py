"""add categories builder ui component

Revision ID: dwh7zeh4dibz
Revises: b2c3d4e5f6a7
Create Date: 2026-03-02 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dwh7zeh4dibz"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add "CategoriesBuilder" value to the ui_component enum
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'CategoriesBuilder'")


def downgrade() -> None:
    pass
