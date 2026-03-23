"""add_qa_sessions_table

Revision ID: 6157153de7cf
Revises: b1c2d3e4f5a7
Create Date: 2026-03-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6157153de7cf"
down_revision: Union[str, None] = "b1c2d3e4f5a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qa_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("graph_runner_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Integer(), nullable=True),
        sa.Column("failed", sa.Integer(), nullable=True),
        sa.Column("error", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["quality_assurance.dataset_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["graph_runner_id"], ["graph_runners.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="quality_assurance",
    )

    op.execute(
        "ALTER TABLE quality_assurance.qa_sessions ALTER COLUMN status TYPE run_status USING status::run_status"
    )

    op.create_index(
        op.f("ix_quality_assurance_qa_sessions_id"),
        "qa_sessions",
        ["id"],
        unique=False,
        schema="quality_assurance",
    )
    op.create_index(
        op.f("ix_quality_assurance_qa_sessions_project_id"),
        "qa_sessions",
        ["project_id"],
        unique=False,
        schema="quality_assurance",
    )
    op.create_index(
        op.f("ix_quality_assurance_qa_sessions_dataset_id"),
        "qa_sessions",
        ["dataset_id"],
        unique=False,
        schema="quality_assurance",
    )
    op.create_index(
        op.f("ix_quality_assurance_qa_sessions_graph_runner_id"),
        "qa_sessions",
        ["graph_runner_id"],
        unique=False,
        schema="quality_assurance",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_quality_assurance_qa_sessions_graph_runner_id"),
        table_name="qa_sessions",
        schema="quality_assurance",
    )
    op.drop_index(
        op.f("ix_quality_assurance_qa_sessions_dataset_id"),
        table_name="qa_sessions",
        schema="quality_assurance",
    )
    op.drop_index(
        op.f("ix_quality_assurance_qa_sessions_project_id"),
        table_name="qa_sessions",
        schema="quality_assurance",
    )
    op.drop_index(
        op.f("ix_quality_assurance_qa_sessions_id"),
        table_name="qa_sessions",
        schema="quality_assurance",
    )
    op.drop_table("qa_sessions", schema="quality_assurance")
