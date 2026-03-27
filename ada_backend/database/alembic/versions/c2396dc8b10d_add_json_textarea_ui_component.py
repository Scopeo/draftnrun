"""add JsonTextarea ui component

Revision ID: c2396dc8b10d
Revises: 6157153de7cf
Create Date: 2026-03-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2396dc8b10d"
down_revision: Union[str, None] = "6157153de7cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'JsonTextarea'")


def downgrade() -> None:
    pass
