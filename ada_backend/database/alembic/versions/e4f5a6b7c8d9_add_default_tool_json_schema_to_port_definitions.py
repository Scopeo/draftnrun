"""add default_tool_json_schema to port_definitions

Revision ID: e4f5a6b7c8d9
Revises: a3b7c9d1e5f2
Create Date: 2026-03-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "e4f5a6b7c8d9"
down_revision = "a3b7c9d1e5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("port_definitions", sa.Column("default_tool_json_schema", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("port_definitions", "default_tool_json_schema")
