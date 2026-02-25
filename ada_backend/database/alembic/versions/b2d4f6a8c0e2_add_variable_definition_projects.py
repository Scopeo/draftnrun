"""add variable definition projects

Revision ID: b2d4f6a8c0e2
Revises: a1c2e3f4b5d6
Create Date: 2026-02-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d4f6a8c0e2"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the association table
    op.create_table(
        "org_variable_definition_projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("definition_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["definition_id"],
            ["org_variable_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("definition_id", "project_id", name="uq_variable_definition_project"),
    )
    op.create_index(
        "ix_org_variable_definition_projects_definition_id",
        "org_variable_definition_projects",
        ["definition_id"],
    )
    op.create_index(
        "ix_org_variable_definition_projects_project_id",
        "org_variable_definition_projects",
        ["project_id"],
    )

    # Migrate existing project_id data into the association table
    op.execute(
        """
        INSERT INTO org_variable_definition_projects (id, definition_id, project_id)
        SELECT gen_random_uuid(), id, project_id
        FROM org_variable_definitions
        WHERE project_id IS NOT NULL
        """
    )

    # Drop the old project_id column and its index
    op.drop_index("ix_org_variable_definitions_project_id", table_name="org_variable_definitions")
    op.drop_column("org_variable_definitions", "project_id")


def downgrade() -> None:
    # Re-add project_id column
    op.add_column(
        "org_variable_definitions",
        sa.Column("project_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_org_variable_definitions_project_id",
        "org_variable_definitions",
        ["project_id"],
    )
    op.create_foreign_key(
        "org_variable_definitions_project_id_fkey",
        "org_variable_definitions",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Migrate first association back to project_id
    op.execute(
        """
        UPDATE org_variable_definitions d
        SET project_id = (
            SELECT project_id
            FROM org_variable_definition_projects p
            WHERE p.definition_id = d.id
            LIMIT 1
        )
        """
    )

    # Drop the association table
    op.drop_table("org_variable_definition_projects")
