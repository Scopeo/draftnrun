"""create variable definitions table

Revision ID: a3b7d9e1f405
Revises: 67ec7c0706ec
Create Date: 2026-02-10 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3b7d9e1f405"
down_revision: Union[str, None] = "67ec7c0706ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create variable_type enum (create_type=False to prevent create_table from duplicating)
    variable_type_enum = postgresql.ENUM(
        "string", "select", "oauth", "email", "number", "boolean",
        name="variable_type",
        create_type=False,
    )
    variable_type_enum.create(op.get_bind(), checkfirst=True)

    # Create project_variable_definitions table
    op.create_table(
        "project_variable_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", variable_type_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("default_value", sa.String(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("editable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_project_variable_definition"),
    )

    op.create_index(op.f("ix_project_variable_definitions_id"), "project_variable_definitions", ["id"], unique=False)
    op.create_index(
        op.f("ix_project_variable_definitions_project_id"),
        "project_variable_definitions",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_variable_definitions_project_id"), table_name="project_variable_definitions")
    op.drop_index(op.f("ix_project_variable_definitions_id"), table_name="project_variable_definitions")
    op.drop_table("project_variable_definitions")

    # Drop the enum type
    postgresql.ENUM(name="variable_type").drop(op.get_bind(), checkfirst=True)
