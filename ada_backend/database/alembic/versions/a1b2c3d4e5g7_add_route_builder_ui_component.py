"""add router component support

Revision ID: a1b2c3d4e5g7
Revises: a1c2e3f4b5d6
Create Date: 2026-02-06 12:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5g7"
down_revision: Union[str, None] = "a1c2e3f4b5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add "RouteBuilder" value to the ui_component enum
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'RouteBuilder'")

    # Add source_port_name column to graph_runner_edges
    op.add_column("graph_runner_edges", sa.Column("source_port_name", sa.String(), nullable=True))


def downgrade() -> None:
    # Remove source_port_name column from graph_runner_edges
    op.drop_column("graph_runner_edges", "source_port_name")

    # Update any existing RouteBuilder components to use CONDITION_BUILDER or JSON_BUILDER
    op.execute(
        """
        UPDATE component_parameter_definitions
        SET ui_component = 'ConditionBuilder'
        WHERE ui_component = 'RouteBuilder'
        """
    )
    op.execute(
        """
        UPDATE port_definitions
        SET ui_component = 'ConditionBuilder'
        WHERE ui_component = 'RouteBuilder'
        """
    )
    # Note: PostgreSQL does not support removing enum values
    # The 'RouteBuilder' value will remain in the enum type even after downgrade
