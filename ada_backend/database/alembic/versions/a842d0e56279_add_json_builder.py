"""add json builder to ui component

Revision ID: 88dcf82ab86
Revises: 8729faf18d1c
Create Date: 2025-10-31 16:15:19.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "88dcf82ab86"
down_revision: Union[str, None] = "8729faf18d1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add "JSON Builder" value to the ui_component enum
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'JSON Builder'")


def downgrade() -> None:

    op.execute(
        """
        UPDATE component_parameter_definitions
        SET ui_component = 'Textarea'
        WHERE ui_component = 'JSON Builder'
    """
    )
    pass
