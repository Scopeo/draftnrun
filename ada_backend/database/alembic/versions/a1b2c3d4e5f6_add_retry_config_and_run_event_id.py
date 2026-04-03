"""add run retry_group_id and run_inputs table

Revision ID: a1b2c3d4e5f9
Revises: c5d6e7f8a9b0
Create Date: 2026-03-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a1b2c3d4e5f9"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"


def upgrade() -> None:
    op.add_column("runs", sa.Column("retry_group_id", sa.UUID(), nullable=True))
    op.add_column("runs", sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"))
    op.create_unique_constraint(
        "uq_runs_retry_group_id_attempt_number",
        "runs",
        ["retry_group_id", "attempt_number"],
    )
    op.create_index(op.f("ix_runs_retry_group_id"), "runs", ["retry_group_id"], unique=False)

    op.create_table(
        "run_inputs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("retry_group_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("input_data", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("retry_group_id", name="uq_run_inputs_retry_group_id"),
    )
    op.create_index(op.f("ix_run_inputs_created_at"), "run_inputs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_run_inputs_created_at"), table_name="run_inputs")
    op.drop_table("run_inputs")
    op.drop_index(op.f("ix_runs_retry_group_id"), table_name="runs")
    op.drop_constraint("uq_runs_retry_group_id_attempt_number", "runs", type_="unique")
    op.drop_column("runs", "attempt_number")
    op.drop_column("runs", "retry_group_id")
