"""add set_type to variable sets

Revision ID: c3e5a7b9d1f4
Revises: f7e8d9c0b1a2
Create Date: 2026-02-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e5a7b9d1f4"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

set_type_enum = sa.Enum("variable", "integration", name="set_type")


def upgrade() -> None:
    set_type_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "org_variable_sets",
        sa.Column("set_type", set_type_enum, nullable=False, server_default="variable"),
    )
    op.add_column(
        "org_variable_sets",
        sa.Column("oauth_connection_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_org_variable_sets_org_set_type",
        "org_variable_sets",
        ["organization_id", "set_type"],
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
    op.drop_index("ix_org_variable_sets_org_set_type", table_name="org_variable_sets")
    op.drop_column("org_variable_sets", "oauth_connection_id")
    op.drop_column("org_variable_sets", "set_type")
    set_type_enum.drop(op.get_bind(), checkfirst=True)
