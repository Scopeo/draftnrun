"""add organization_id to qa tables

Revision ID: a1b2c3d4e5f7
Revises: b7e8f9a0c1d2
Create Date: 2026-02-09 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "b7e8f9a0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add organization_id columns (nullable initially for data migration)
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

    # Step 2: Populate organization_id from project's organization
    op.execute("""
        UPDATE quality_assurance.dataset_project
        SET organization_id = (
            SELECT organization_id FROM projects WHERE id = dataset_project.project_id
        )
        WHERE project_id IS NOT NULL
    """)

    op.execute("""
        UPDATE quality_assurance.llm_judges
        SET organization_id = (
            SELECT organization_id FROM projects WHERE id = llm_judges.project_id
        )
        WHERE project_id IS NOT NULL
    """)

    # Step 3: Make organization_id NOT NULL
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

    # Step 4: Make project_id nullable (for backward compatibility)
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

    # Step 5: Add indexes on organization_id
    op.create_index(
        op.f("ix_quality_assurance_dataset_project_organization_id"),
        "dataset_project",
        ["organization_id"],
        unique=False,
        schema="quality_assurance",
    )
    op.create_index(
        op.f("ix_quality_assurance_llm_judges_organization_id"),
        "llm_judges",
        ["organization_id"],
        unique=False,
        schema="quality_assurance",
    )


def downgrade() -> None:
    # Remove indexes
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

    # Delete records without project_id (created while organization_id was the primary reference)
    op.execute("DELETE FROM quality_assurance.dataset_project WHERE project_id IS NULL")
    op.execute("DELETE FROM quality_assurance.llm_judges WHERE project_id IS NULL")

    # Make project_id NOT NULL again
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

    # Remove organization_id columns
    op.drop_column("llm_judges", "organization_id", schema="quality_assurance")
    op.drop_column("dataset_project", "organization_id", schema="quality_assurance")
