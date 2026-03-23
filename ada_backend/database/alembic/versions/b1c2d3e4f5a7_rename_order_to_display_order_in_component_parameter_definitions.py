"""Rename order to display_order in component_parameter_definitions

Revision ID: b1c2d3e4f5a7
Revises: b4c5d6e7f8a9
Create Date: 2026-03-23 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b1c2d3e4f5a7"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("component_parameter_definitions", "order", new_column_name="display_order")


def downgrade() -> None:
    op.alter_column("component_parameter_definitions", "display_order", new_column_name="order")
