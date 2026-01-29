"""json_equality as an evaluation

Revision ID: fe1c665d7821
Revises: d5e6f7a8b9c0
Create Date: 2026-01-29 16:59:16.630422

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fe1c665d7821'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE evaluation_type ADD VALUE IF NOT EXISTS 'json_equality'")


def downgrade() -> None:
    pass
