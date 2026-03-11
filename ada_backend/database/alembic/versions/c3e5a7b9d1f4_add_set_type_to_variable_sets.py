"""add variable_type to variable sets

Revision ID: c3e5a7b9d1f4
Revises: c4d5e6f7a8b9
Create Date: 2026-02-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e5a7b9d1f4"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

variable_type_enum = sa.Enum(
    "string", "oauth", "number", "boolean", "secret", "source", "variable",
    name="variable_type",
    create_type=False,
)


def upgrade() -> None:
    # New enum values must be committed before they can be used (PG requirement).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE variable_type ADD VALUE IF NOT EXISTS 'variable'")

    op.add_column(
        "org_variable_sets",
        sa.Column("variable_type", variable_type_enum, nullable=False, server_default="variable"),
    )
    op.add_column(
        "org_variable_sets",
        sa.Column("oauth_connection_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_org_variable_sets_org_variable_type",
        "org_variable_sets",
        ["organization_id", "variable_type"],
    )
    op.create_index(
        "ix_org_variable_sets_oauth_connection_id",
        "org_variable_sets",
        ["oauth_connection_id"],
    )
    op.create_foreign_key(
        "fk_org_variable_sets_oauth_connection_id",
        "org_variable_sets",
        "oauth_connections",
        ["oauth_connection_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_org_variable_sets_oauth_connection_id", "org_variable_sets", type_="foreignkey")
    op.drop_index("ix_org_variable_sets_oauth_connection_id", table_name="org_variable_sets")
    op.drop_index("ix_org_variable_sets_org_variable_type", table_name="org_variable_sets")
    op.drop_column("org_variable_sets", "oauth_connection_id")
    op.drop_column("org_variable_sets", "variable_type")
