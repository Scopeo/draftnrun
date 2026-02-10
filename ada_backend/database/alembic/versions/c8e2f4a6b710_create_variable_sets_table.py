"""create variable sets table

Revision ID: c8e2f4a6b710
Revises: a3b7d9e1f405
Create Date: 2026-02-10 00:01:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c8e2f4a6b710"
down_revision: Union[str, None] = "a3b7d9e1f405"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_variable_sets",
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

    op.create_index(op.f("ix_project_variable_sets_id"), "project_variable_sets", ["id"], unique=False)
    op.create_index(
        op.f("ix_project_variable_sets_organization_id"),
        "project_variable_sets",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_variable_sets_project_id"),
        "project_variable_sets",
        ["project_id"],
        unique=False,
    )

    # Partial unique index for future project-level scoping
    op.create_index(
        "uq_project_variable_set",
        "project_variable_sets",
        ["project_id", "set_id"],
        unique=True,
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_project_variable_set", table_name="project_variable_sets")
    op.drop_index(op.f("ix_project_variable_sets_project_id"), table_name="project_variable_sets")
    op.drop_index(op.f("ix_project_variable_sets_organization_id"), table_name="project_variable_sets")
    op.drop_index(op.f("ix_project_variable_sets_id"), table_name="project_variable_sets")
    op.drop_table("project_variable_sets")
