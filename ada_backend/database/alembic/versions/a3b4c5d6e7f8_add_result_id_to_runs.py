"""add_result_id_to_runs

Revision ID: a3b4c5d6e7f8
Revises: f7e8d9c0b1a2
Create Date: 2026-03-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f7e8d9c0b1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("result_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "result_id")
