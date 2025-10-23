"""migrate api input to start component in spans

Revision ID: 20250adc5a87
Revises: 7a9e2b3f4c5d
Create Date: 2025-01-03 00:00:01.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20250adc5a87"
down_revision: Union[str, None] = "55bf7791d9dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update span names from "API Input" to "Start" in the spans table
    op.execute(
        """
        UPDATE spans 
        SET name = 'Start' 
        WHERE name = 'API Input'
        """
    )


def downgrade() -> None:
    # Revert span names from "Start" back to "API Input" in the spans table
    op.execute(
        """
        UPDATE spans 
        SET name = 'API Input' 
        WHERE name = 'Start'
        """
    )
