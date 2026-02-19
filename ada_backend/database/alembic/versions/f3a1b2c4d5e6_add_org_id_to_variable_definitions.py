"""add variable definitions and variable sets tables

Revision ID: f3a1b2c4d5e6
Revises: 7055cd620c33
Create Date: 2026-02-10 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3a1b2c4d5e6"
down_revision: Union[str, None] = "300e0970e3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create variable_type enum (includes 'secret')
    variable_type_enum = postgresql.ENUM(
        "string", "oauth", "number", "boolean", "secret", "source",
        name="variable_type",
        create_type=False,
    )
    variable_type_enum.create(op.get_bind(), checkfirst=True)

    # Create org_variable_definitions table (org-scoped, optional project tag)
    op.create_table(
        "org_variable_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint("organization_id", "name", name="uq_org_variable_definition"),
    )

    op.create_index(
        op.f("ix_org_variable_definitions_project_id"),
        "org_variable_definitions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_org_variable_definitions_organization_id"),
        "org_variable_definitions",
        ["organization_id"],
        unique=False,
    )

    # Create org_variable_sets table
    op.create_table(
        "org_variable_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("set_id", sa.String(), nullable=False),
        sa.Column("values", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "set_id", name="uq_org_variable_set"),
    )

    op.create_index(
        op.f("ix_org_variable_sets_organization_id"),
        "org_variable_sets",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_org_variable_sets_project_id"),
        "org_variable_sets",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "uq_org_variable_set_project",
        "org_variable_sets",
        ["project_id", "set_id"],
        unique=True,
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Drop variable sets
    op.drop_index("uq_org_variable_set_project", table_name="org_variable_sets")
    op.drop_index(op.f("ix_org_variable_sets_project_id"), table_name="org_variable_sets")
    op.drop_index(op.f("ix_org_variable_sets_organization_id"), table_name="org_variable_sets")
    op.drop_table("org_variable_sets")

    # Drop variable definitions
    op.drop_index(op.f("ix_org_variable_definitions_organization_id"), table_name="org_variable_definitions")
    op.drop_index(op.f("ix_org_variable_definitions_project_id"), table_name="org_variable_definitions")
    op.drop_table("org_variable_definitions")

    # Drop the enum type
    postgresql.ENUM(name="variable_type").drop(op.get_bind(), checkfirst=True)
