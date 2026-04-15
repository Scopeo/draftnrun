"""create_git_sync_configs_table

Revision ID: g1h2i3j4k5l6
Revises: g6h7i8j9k0l1
Create Date: 2026-04-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "g6h7i8j9k0l1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "git_sync_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("github_owner", sa.String(255), nullable=False),
        sa.Column("github_repo_name", sa.String(255), nullable=False),
        sa.Column("graph_folder", sa.String(500), nullable=False),
        sa.Column("branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("github_installation_id", sa.Integer(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(50), nullable=True),
        sa.Column("last_sync_commit_sha", sa.String(40), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "github_owner", "github_repo_name", "graph_folder", "branch", name="uq_git_sync_graph_folder"
        ),
        sa.UniqueConstraint("project_id", name="uq_git_sync_project"),
    )
    op.create_index(op.f("ix_git_sync_configs_id"), "git_sync_configs", ["id"])
    op.create_index(op.f("ix_git_sync_configs_organization_id"), "git_sync_configs", ["organization_id"])
    op.create_index(op.f("ix_git_sync_configs_github_installation_id"), "git_sync_configs", ["github_installation_id"])
    op.create_index(
        "ix_git_sync_configs_repo_branch", "git_sync_configs", ["github_owner", "github_repo_name", "branch"]
    )


def downgrade() -> None:
    op.drop_index("ix_git_sync_configs_repo_branch", table_name="git_sync_configs")
    op.drop_index(op.f("ix_git_sync_configs_github_installation_id"), table_name="git_sync_configs")
    op.drop_index(op.f("ix_git_sync_configs_organization_id"), table_name="git_sync_configs")
    op.drop_index(op.f("ix_git_sync_configs_id"), table_name="git_sync_configs")
    op.drop_table("git_sync_configs")
