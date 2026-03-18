"""Add order and group fields to port definitions

Revision ID: a3b4c5d6e7e8
Revises: 19f9fe79128a
Create Date: 2026-03-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7e8"
down_revision: Union[str, None] = "19f9fe79128a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("port_definitions", sa.Column("display_order", sa.Integer(), nullable=True))
    op.add_column("port_definitions", sa.Column("parameter_group_id", sa.UUID(), nullable=True))
    op.add_column("port_definitions", sa.Column("parameter_order_within_group", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_port_definitions_parameter_group_id",
        "port_definitions",
        "parameter_groups",
        ["parameter_group_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_port_definitions_parameter_group_id", "port_definitions", type_="foreignkey")
    op.drop_column("port_definitions", "parameter_order_within_group")
    op.drop_column("port_definitions", "parameter_group_id")
    op.drop_column("port_definitions", "display_order")
