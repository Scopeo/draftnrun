"""add_graph_runner_id_to_runs

Revision ID: l3m4n5o6p7q8
Revises: 93189a98fdf2
Create Date: 2026-04-27

deploy_strategy: migrate-first
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l3m4n5o6p7q8"
down_revision: Union[str, None] = "93189a98fdf2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("graph_runner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_runs_graph_runner_id",
        "runs",
        "graph_runners",
        ["graph_runner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_runs_graph_runner_id", "runs", ["graph_runner_id"])


def downgrade() -> None:
    op.drop_index("ix_runs_graph_runner_id", table_name="runs")
    op.drop_constraint("fk_runs_graph_runner_id", "runs", type_="foreignkey")
    op.drop_column("runs", "graph_runner_id")
