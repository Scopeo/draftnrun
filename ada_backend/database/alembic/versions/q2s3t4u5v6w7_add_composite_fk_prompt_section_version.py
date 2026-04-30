"""Add composite FK on prompt_sections (section_prompt_id, section_prompt_version_id)
referencing prompt_versions (prompt_id, id), with supporting unique constraint.

Revision ID: q2s3t4u5v6w7
Revises: p1r2o3m4p5t6
Create Date: 2026-04-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "q2s3t4u5v6w7"
down_revision: Union[str, None] = "p1r2o3m4p5t6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_prompt_version_promptid_id",
        "prompt_versions",
        ["prompt_id", "id"],
    )

    op.drop_constraint(
        "prompt_sections_section_prompt_version_id_fkey",
        "prompt_sections",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_prompt_section_version_prompt",
        "prompt_sections",
        "prompt_versions",
        ["section_prompt_id", "section_prompt_version_id"],
        ["prompt_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_prompt_section_version_prompt",
        "prompt_sections",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "prompt_sections_section_prompt_version_id_fkey",
        "prompt_sections",
        "prompt_versions",
        ["section_prompt_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "uq_prompt_version_promptid_id",
        "prompt_versions",
        type_="unique",
    )
