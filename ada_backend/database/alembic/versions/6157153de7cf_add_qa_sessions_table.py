"""add_qa_sessions_table

Revision ID: 6157153de7cf
Revises: a9c3d2e1f0b4
Create Date: 2026-03-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6157153de7cf"
down_revision: Union[str, None] = "a9c3d2e1f0b4"
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
        "ix_qa_sessions_project_created",
        "qa_sessions",
        ["project_id", sa.text("created_at DESC")],
        unique=False,
        schema="quality_assurance",
    )
    op.create_index(
        "ix_qa_sessions_project_dataset_created",
        "qa_sessions",
        ["project_id", "dataset_id", sa.text("created_at DESC")],
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

    op.add_column(
        "version_output",
        sa.Column("qa_session_id", sa.UUID(), nullable=True),
        schema="quality_assurance",
    )
    op.create_foreign_key(
        "fk_version_output_qa_session",
        "version_output",
        "qa_sessions",
        ["qa_session_id"],
        ["id"],
        source_schema="quality_assurance",
        referent_schema="quality_assurance",
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_quality_assurance_version_output_qa_session_id"),
        "version_output",
        ["qa_session_id"],
        unique=False,
        schema="quality_assurance",
    )

    op.drop_constraint(
        "uq_version_output_input_graph_runner",
        "version_output",
        schema="quality_assurance",
        type_="unique",
    )
    op.create_index(
        "uq_version_output_input_session",
        "version_output",
        ["input_id", "qa_session_id"],
        unique=True,
        schema="quality_assurance",
        postgresql_where=sa.text("qa_session_id IS NOT NULL"),
    )
    op.create_index(
        "uq_version_output_input_graph_runner_no_session",
        "version_output",
        ["input_id", "graph_runner_id"],
        unique=True,
        schema="quality_assurance",
        postgresql_where=sa.text("qa_session_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_version_output_input_graph_runner_no_session",
        table_name="version_output",
        schema="quality_assurance",
    )
    op.drop_index(
        "uq_version_output_input_session",
        table_name="version_output",
        schema="quality_assurance",
    )
    op.create_unique_constraint(
        "uq_version_output_input_graph_runner",
        "version_output",
        ["input_id", "graph_runner_id"],
        schema="quality_assurance",
    )
    op.drop_index(
        op.f("ix_quality_assurance_version_output_qa_session_id"),
        table_name="version_output",
        schema="quality_assurance",
    )
    op.drop_constraint(
        "fk_version_output_qa_session",
        "version_output",
        schema="quality_assurance",
        type_="foreignkey",
    )
    op.drop_column("version_output", "qa_session_id", schema="quality_assurance")

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
        "ix_qa_sessions_project_dataset_created",
        table_name="qa_sessions",
        schema="quality_assurance",
    )
    op.drop_index(
        "ix_qa_sessions_project_created",
        table_name="qa_sessions",
        schema="quality_assurance",
    )
    op.drop_table("qa_sessions", schema="quality_assurance")
