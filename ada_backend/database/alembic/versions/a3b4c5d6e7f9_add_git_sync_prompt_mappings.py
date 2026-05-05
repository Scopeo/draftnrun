"""Add git_sync_prompt_mappings table for syncing prompts from GitHub repos.

Revision ID: a3b4c5d6e7f9
Revises: 88538199bc7b
Create Date: 2026-05-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f9"
down_revision: Union[str, None] = "88538199bc7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"


def upgrade() -> None:
    op.create_table(
        "git_sync_prompt_mappings",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("organization_id", sa.UUID(), nullable=False, index=True),
        sa.Column(
            "prompt_definition_id",
            sa.UUID(),
            sa.ForeignKey("prompt_definitions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("github_owner", sa.String(255), nullable=False),
        sa.Column("github_repo_name", sa.String(255), nullable=False),
        sa.Column("branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("prompt_file_path", sa.String(500), nullable=False),
        sa.Column("github_installation_id", sa.Integer(), nullable=False, index=True),
        sa.Column("last_sync_commit_sha", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "github_owner",
            "github_repo_name",
            "branch",
            "prompt_file_path",
            name="uq_git_sync_prompt_file",
        ),
    )
    op.create_index(
        "ix_git_sync_prompt_mappings_repo_branch",
        "git_sync_prompt_mappings",
        ["github_owner", "github_repo_name", "branch"],
    )


def downgrade() -> None:
    op.drop_index("ix_git_sync_prompt_mappings_repo_branch", table_name="git_sync_prompt_mappings")
    op.drop_table("git_sync_prompt_mappings")
