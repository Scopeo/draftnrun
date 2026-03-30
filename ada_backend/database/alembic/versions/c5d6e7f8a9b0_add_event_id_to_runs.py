"""add_event_id_to_runs

Revision ID: c5d6e7f8a9b0
Revises: f5a6b7c8d9e0
Create Date: 2026-03-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("event_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_runs_event_id"), "runs", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_runs_event_id"), table_name="runs")
    op.drop_column("runs", "event_id")
