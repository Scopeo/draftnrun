"""add route builder ui component

Revision ID: a1b2c3d4e5f7
Revises: fe1c665d7821
Create Date: 2026-02-06 12:20:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "fe1c665d7821"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add "RouteBuilder" value to the ui_component enum
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'RouteBuilder'")


def downgrade() -> None:
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
