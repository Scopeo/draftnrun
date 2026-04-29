"""Add prompt library: prompts, prompt_versions, prompt_sections tables,
is_prompt column on port_definitions, prompt_version_id on input_port_instances.

Revision ID: p1r2o3m4p5t6
Revises: 93189a98fdf2
Create Date: 2026-04-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p1r2o3m4p5t6"
down_revision: Union[str, None] = "93189a98fdf2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("organization_id", sa.UUID(), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_prompts_org_name", "prompts", ["organization_id", "name"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("prompt_id", sa.UUID(), sa.ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("change_description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("prompt_id", "version_number", name="uq_prompt_version_number"),
    )

    op.create_table(
        "prompt_sections",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "prompt_version_id",
            sa.UUID(),
            sa.ForeignKey("prompt_versions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "section_prompt_id", sa.UUID(), sa.ForeignKey("prompts.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "section_prompt_version_id",
            sa.UUID(),
            sa.ForeignKey("prompt_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("placeholder", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("prompt_version_id", "placeholder", name="uq_prompt_section_placeholder"),
    )

    op.add_column("port_definitions", sa.Column("is_prompt", sa.Boolean(), nullable=False, server_default="false"))

    op.add_column(
        "input_port_instances",
        sa.Column(
            "prompt_version_id",
            sa.UUID(),
            sa.ForeignKey("prompt_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_input_port_instances_prompt_version_id", "input_port_instances", ["prompt_version_id"])


def downgrade() -> None:
    op.drop_index("ix_input_port_instances_prompt_version_id", table_name="input_port_instances")
    op.drop_column("input_port_instances", "prompt_version_id")
    op.drop_column("port_definitions", "is_prompt")
    op.drop_table("prompt_sections")
    op.drop_table("prompt_versions")
    op.drop_index("ix_prompts_org_name", table_name="prompts")
    op.drop_table("prompts")
