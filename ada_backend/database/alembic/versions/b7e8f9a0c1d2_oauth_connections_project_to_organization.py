"""oauth_connections_project_to_organization

Revision ID: b7e8f9a0c1d2
Revises: 67ec7c0706ec
Create Date: 2026-02-10

Migrates OAuth connections from project-scoped to organization-scoped.
Existing connections are preserved by mapping project_id -> project.organization_id.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e8f9a0c1d2"
down_revision: Union[str, None] = "hc4u6epu6y03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "oauth_connections",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE oauth_connections
        SET organization_id = projects.organization_id
        FROM projects
        WHERE projects.id = oauth_connections.project_id
        """
    )
    op.alter_column(
        "oauth_connections",
        "organization_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_constraint("oauth_connections_project_id_fkey", "oauth_connections", type_="foreignkey")
    op.drop_index(op.f("ix_oauth_connections_project_id"), table_name="oauth_connections")
    op.drop_column("oauth_connections", "project_id")
    op.create_index(
        op.f("ix_oauth_connections_organization_id"),
        "oauth_connections",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.execute("TRUNCATE TABLE oauth_connections")
    op.drop_index(op.f("ix_oauth_connections_organization_id"), table_name="oauth_connections")
    op.drop_column("oauth_connections", "organization_id")
    op.add_column(
        "oauth_connections",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_index(op.f("ix_oauth_connections_project_id"), "oauth_connections", ["project_id"], unique=False)
    op.create_foreign_key(
        "oauth_connections_project_id_fkey",
        "oauth_connections",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
