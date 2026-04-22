"""Move QA datasets and LLM judges from project-scoped to organization-scoped.

Adds organization_id to dataset_project and llm_judges, creates association
tables for the many-to-many project mapping, backfills all data, and makes
project_id nullable (to be dropped in a follow-up migration).

Revision ID: i8j9k0l1m2n3
Revises: j1k2l3m4n5o6
Create Date: 2026-04-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i8j9k0l1m2n3"
down_revision: Union[str, None] = "j1k2l3m4n5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"


def upgrade() -> None:
    # --- 1. Add organization_id (nullable for now) ---
    op.add_column(
        "dataset_project",
        sa.Column("organization_id", sa.UUID(), nullable=True),
        schema="quality_assurance",
    )
    op.add_column(
        "llm_judges",
        sa.Column("organization_id", sa.UUID(), nullable=True),
        schema="quality_assurance",
    )

    # --- 2. Backfill organization_id from projects.organization_id ---
    op.execute(
        """
        UPDATE quality_assurance.dataset_project dp
        SET organization_id = p.organization_id
        FROM projects p
        WHERE dp.project_id = p.id
        """
    )
    op.execute(
        """
        UPDATE quality_assurance.llm_judges lj
        SET organization_id = p.organization_id
        FROM projects p
        WHERE lj.project_id = p.id
        """
    )

    # --- 3. Make organization_id non-nullable and add index ---
    op.alter_column(
        "dataset_project",
        "organization_id",
        nullable=False,
        schema="quality_assurance",
    )
    op.alter_column(
        "llm_judges",
        "organization_id",
        nullable=False,
        schema="quality_assurance",
    )
    op.create_index(
        op.f("ix_quality_assurance_dataset_project_organization_id"),
        "dataset_project",
        ["organization_id"],
        schema="quality_assurance",
    )
    op.create_index(
        op.f("ix_quality_assurance_llm_judges_organization_id"),
        "llm_judges",
        ["organization_id"],
        schema="quality_assurance",
    )

    # --- 4. Create association tables ---
    op.create_table(
        "dataset_project_associations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.UUID(),
            sa.ForeignKey("quality_assurance.dataset_project.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.UniqueConstraint("dataset_id", "project_id", name="uq_dataset_project_association"),
        schema="quality_assurance",
    )
    op.create_table(
        "llm_judge_project_associations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "judge_id",
            sa.UUID(),
            sa.ForeignKey("quality_assurance.llm_judges.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.UniqueConstraint("judge_id", "project_id", name="uq_llm_judge_project_association"),
        schema="quality_assurance",
    )

    # --- 5. Backfill association tables from existing project_id ---
    op.execute(
        """
        INSERT INTO quality_assurance.dataset_project_associations (dataset_id, project_id)
        SELECT id, project_id
        FROM quality_assurance.dataset_project
        WHERE project_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO quality_assurance.llm_judge_project_associations (judge_id, project_id)
        SELECT id, project_id
        FROM quality_assurance.llm_judges
        WHERE project_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    # --- 6. Make project_id nullable and fix FK to SET NULL ---
    op.alter_column(
        "dataset_project",
        "project_id",
        nullable=True,
        schema="quality_assurance",
    )
    op.alter_column(
        "llm_judges",
        "project_id",
        nullable=True,
        schema="quality_assurance",
    )

    op.drop_constraint(
        "dataset_project_project_id_fkey",
        "dataset_project",
        schema="quality_assurance",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "dataset_project_project_id_fkey",
        "dataset_project",
        "projects",
        ["project_id"],
        ["id"],
        source_schema="quality_assurance",
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "llm_judges_project_id_fkey",
        "llm_judges",
        schema="quality_assurance",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "llm_judges_project_id_fkey",
        "llm_judges",
        "projects",
        ["project_id"],
        ["id"],
        source_schema="quality_assurance",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Backfill project_id from association tables for rows that were set to NULL
    op.execute(
        """
        UPDATE quality_assurance.dataset_project dp
        SET project_id = dpa.project_id
        FROM quality_assurance.dataset_project_associations dpa
        WHERE dp.id = dpa.dataset_id
          AND dp.project_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE quality_assurance.llm_judges lj
        SET project_id = ljpa.project_id
        FROM quality_assurance.llm_judge_project_associations ljpa
        WHERE lj.id = ljpa.judge_id
          AND lj.project_id IS NULL
        """
    )

    # Remove any rows that still lack a project_id (created after migration, no association)
    op.execute("DELETE FROM quality_assurance.dataset_project WHERE project_id IS NULL")
    op.execute("DELETE FROM quality_assurance.llm_judges WHERE project_id IS NULL")

    op.drop_constraint(
        "llm_judges_project_id_fkey",
        "llm_judges",
        schema="quality_assurance",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "llm_judges_project_id_fkey",
        "llm_judges",
        "projects",
        ["project_id"],
        ["id"],
        source_schema="quality_assurance",
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "dataset_project_project_id_fkey",
        "dataset_project",
        schema="quality_assurance",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "dataset_project_project_id_fkey",
        "dataset_project",
        "projects",
        ["project_id"],
        ["id"],
        source_schema="quality_assurance",
        ondelete="CASCADE",
    )

    op.alter_column(
        "llm_judges",
        "project_id",
        nullable=False,
        schema="quality_assurance",
    )
    op.alter_column(
        "dataset_project",
        "project_id",
        nullable=False,
        schema="quality_assurance",
    )

    op.drop_table("llm_judge_project_associations", schema="quality_assurance")
    op.drop_table("dataset_project_associations", schema="quality_assurance")

    op.drop_index(
        op.f("ix_quality_assurance_llm_judges_organization_id"),
        table_name="llm_judges",
        schema="quality_assurance",
    )
    op.drop_index(
        op.f("ix_quality_assurance_dataset_project_organization_id"),
        table_name="dataset_project",
        schema="quality_assurance",
    )

    op.drop_column("llm_judges", "organization_id", schema="quality_assurance")
    op.drop_column("dataset_project", "organization_id", schema="quality_assurance")
