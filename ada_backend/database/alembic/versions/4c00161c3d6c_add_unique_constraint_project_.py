"""add_unique_constraint_project_environment

Revision ID: 4c00161c3d6c
Revises: 1cd27a655140
Create Date: 2025-10-15 17:52:30.304427

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "4c00161c3d6c"
down_revision: Union[str, None] = "1cd27a655140"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        text(
            """
            WITH ranked_bindings AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY project_id, environment
                           ORDER BY created_at DESC, id DESC
                       ) as rn
                FROM project_env_binding
                WHERE environment IS NOT NULL
            )
            DELETE FROM project_env_binding
            WHERE id IN (
                SELECT id FROM ranked_bindings WHERE rn > 1
            )
            """
        )
    )

    op.create_unique_constraint(
        "uq_project_environment",
        "project_env_binding",
        ["project_id", "environment"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_project_environment", "project_env_binding", type_="unique")
