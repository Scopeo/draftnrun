"""Create project_tags table.

deploy_strategy = "migrate-first"

Revision ID: i1j2k3l4m5n6
Revises: h7i8j9k0l1m2
Create Date: 2026-04-16
"""

import sqlalchemy as sa
from alembic import op

revision = "i1j2k3l4m5n6"
down_revision = "h7i8j9k0l1m2"
branch_labels = None
depends_on = None

deploy_strategy = "migrate-first"


def upgrade() -> None:
    op.create_table(
        "project_tags",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "tag", name="uq_project_tags_project_id_tag"),
    )
    op.create_index("ix_project_tags_project_id", "project_tags", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_tags_project_id", table_name="project_tags")
    op.drop_table("project_tags")
