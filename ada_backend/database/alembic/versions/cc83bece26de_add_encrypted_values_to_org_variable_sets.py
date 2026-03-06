"""add variable secrets to organization_secrets

Revision ID: cc83bece26de
Revises: 3079a5433670
Create Date: 2026-03-06 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "cc83bece26de"
down_revision: Union[str, None] = "3079a5433670"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Must commit before using the new enum value in DML (PostgreSQL limitation)
    op.execute("ALTER TYPE org_secret_type ADD VALUE IF NOT EXISTS 'variable'")
    op.execute("COMMIT")

    op.add_column(
        "organization_secrets",
        sa.Column("variable_definition_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "organization_secrets",
        sa.Column("variable_set_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_org_secret_variable_definition",
        "organization_secrets",
        "org_variable_definitions",
        ["variable_definition_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_org_secret_variable_set",
        "organization_secrets",
        "org_variable_sets",
        ["variable_set_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_org_secret_variable
        ON organization_secrets (variable_definition_id, variable_set_id)
        NULLS NOT DISTINCT
        WHERE variable_definition_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_org_secret_variable")
    op.drop_constraint("fk_org_secret_variable_definition", "organization_secrets", type_="foreignkey")
    op.drop_constraint("fk_org_secret_variable_set", "organization_secrets", type_="foreignkey")
    op.drop_column("organization_secrets", "variable_definition_id")
    op.drop_column("organization_secrets", "variable_set_id")
    # Note: cannot remove 'variable' from org_secret_type enum in PostgreSQL
