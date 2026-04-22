"""create_github_app_installations_table

Revision ID: j1k2l3m4n5o6
Revises: i1j2k3l4m5n6
Create Date: 2026-04-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, None] = "i1j2k3l4m5n6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
deploy_strategy: str = "migrate-first"


def upgrade() -> None:
    op.create_table(
        "github_app_installations",
        sa.Column("github_installation_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("github_installation_id"),
    )
    op.create_index(
        op.f("ix_github_app_installations_organization_id"),
        "github_app_installations",
        ["organization_id"],
    )

    conn = op.get_bind()
    conflicts = conn.execute(
        sa.text(
            """
            SELECT github_installation_id
            FROM git_sync_configs
            GROUP BY github_installation_id
            HAVING COUNT(DISTINCT organization_id) > 1
            """
        )
    ).fetchall()

    if conflicts:
        ids = ", ".join(str(row[0]) for row in conflicts)
        raise RuntimeError(
            f"Cannot migrate: github_installation_id(s) [{ids}] are linked to "
            f"multiple organizations in git_sync_configs. Resolve the conflicting "
            f"ownership before re-running this migration."
        )

    op.execute(
        """
        INSERT INTO github_app_installations (github_installation_id, organization_id)
        SELECT DISTINCT github_installation_id, organization_id
        FROM git_sync_configs
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_github_app_installations_organization_id"), table_name="github_app_installations")
    op.drop_table("github_app_installations")
