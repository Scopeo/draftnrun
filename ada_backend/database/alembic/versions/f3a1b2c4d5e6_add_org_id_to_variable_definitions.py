"""add organization_id to variable definitions and make project_id nullable

Revision ID: f3a1b2c4d5e6
Revises: 62d077615136
Create Date: 2026-02-10 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a1b2c4d5e6"
down_revision: Union[str, None] = "d5f1a8c3e927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add organization_id column (nullable initially for backfill)
    op.add_column(
        "project_variable_definitions",
        sa.Column("organization_id", sa.UUID(), nullable=True),
    )

    # 2. Backfill organization_id from projects table
    op.execute(
        """
        UPDATE project_variable_definitions pvd
        SET organization_id = p.organization_id
        FROM projects p
        WHERE pvd.project_id = p.id
        """
    )

    # 3. Make organization_id NOT NULL
    op.alter_column("project_variable_definitions", "organization_id", nullable=False)

    # 4. Make project_id nullable
    op.alter_column("project_variable_definitions", "project_id", nullable=True)

    # 5. Add index on organization_id
    op.create_index(
        op.f("ix_project_variable_definitions_organization_id"),
        "project_variable_definitions",
        ["organization_id"],
        unique=False,
    )

    # 6. Drop old unique constraint and add new one
    op.drop_constraint("uq_project_variable_definition", "project_variable_definitions", type_="unique")
    op.create_unique_constraint(
        "uq_org_variable_definition",
        "project_variable_definitions",
        ["organization_id", "name"],
    )


def downgrade() -> None:
    # Remove rows without project_id (org-only definitions)
    op.execute(
        """
        DELETE FROM project_variable_definitions WHERE project_id IS NULL
        """
    )

    # Reverse constraint changes
    op.drop_constraint("uq_org_variable_definition", "project_variable_definitions", type_="unique")
    op.create_unique_constraint(
        "uq_project_variable_definition",
        "project_variable_definitions",
        ["project_id", "name"],
    )

    # Make project_id NOT NULL again
    op.alter_column("project_variable_definitions", "project_id", nullable=False)

    # Drop organization_id
    op.drop_index(
        op.f("ix_project_variable_definitions_organization_id"),
        table_name="project_variable_definitions",
    )
    op.drop_column("project_variable_definitions", "organization_id")
