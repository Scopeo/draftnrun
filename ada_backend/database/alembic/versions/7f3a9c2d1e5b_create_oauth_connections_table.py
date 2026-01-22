"""create_oauth_connections_table

Revision ID: 7f3a9c2d1e5b
Revises: 6414df8fbe91
Create Date: 2026-01-29 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7f3a9c2d1e5b"
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create oauth_connections table
    op.create_table(
        "oauth_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_config_key", sa.String(length=255), nullable=False),
        sa.Column("nango_connection_id", sa.String(length=500), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(op.f("ix_oauth_connections_id"), "oauth_connections", ["id"], unique=False)
    op.create_index(op.f("ix_oauth_connections_project_id"), "oauth_connections", ["project_id"], unique=False)
    op.create_index(
        op.f("ix_oauth_connections_provider_config_key"), "oauth_connections", ["provider_config_key"], unique=False
    )
    op.create_index(
        op.f("ix_oauth_connections_nango_connection_id"), "oauth_connections", ["nango_connection_id"], unique=True
    )
    op.create_index(
        op.f("ix_oauth_connections_created_by_user_id"), "oauth_connections", ["created_by_user_id"], unique=False
    )
    op.create_index(op.f("ix_oauth_connections_deleted_at"), "oauth_connections", ["deleted_at"], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f("ix_oauth_connections_deleted_at"), table_name="oauth_connections")
    op.drop_index(op.f("ix_oauth_connections_created_by_user_id"), table_name="oauth_connections")
    op.drop_index(op.f("ix_oauth_connections_nango_connection_id"), table_name="oauth_connections")
    op.drop_index(op.f("ix_oauth_connections_provider_config_key"), table_name="oauth_connections")
    op.drop_index(op.f("ix_oauth_connections_project_id"), table_name="oauth_connections")
    op.drop_index(op.f("ix_oauth_connections_id"), table_name="oauth_connections")

    # Drop table
    op.drop_table("oauth_connections")
