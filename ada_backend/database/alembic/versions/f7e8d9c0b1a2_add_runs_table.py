"""add_runs_table

Revision ID: f7e8d9c0b1a2
Revises: b2c3d4e5f6a7
Create Date: 2026-03-02 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ada_backend.database.utils import create_enum_if_not_exists, drop_enum_if_exists

# revision identifiers, used by Alembic.
revision: str = "f7e8d9c0b1a2"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    create_enum_if_not_exists(
        connection=op.get_bind(),
        enum_values=["pending", "running", "completed", "failed"],
        enum_name="run_status",
    )
    # Reuse call_type enum (api, sandbox, qa); add webhook for run trigger
    op.execute("ALTER TYPE call_type ADD VALUE IF NOT EXISTS 'webhook'")
    run_status_enum = postgresql.ENUM(
        "pending",
        "running",
        "completed",
        "failed",
        name="run_status",
        create_type=False,
    )
    call_type_enum = postgresql.ENUM(
        "api",
        "sandbox",
        "qa",
        "webhook",
        name="call_type",
        create_type=False,
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("status", run_status_enum, nullable=False, server_default="pending"),
        sa.Column("trigger", call_type_enum, nullable=False, server_default="api"),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runs_id"), "runs", ["id"], unique=False)
    op.create_index(op.f("ix_runs_project_id"), "runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_runs_trace_id"), "runs", ["trace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_runs_trace_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_project_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_id"), table_name="runs")
    op.drop_table("runs")
    drop_enum_if_exists(connection=op.get_bind(), enum_name="run_status")
    # Note: call_type enum keeps 'webhook'; Postgres does not support removing enum values
