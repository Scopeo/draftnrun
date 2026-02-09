"""add nullable to port definitions

Revision ID: 67ec7c0706ec
Revises: 8daad1874818
Create Date: 2026-02-09 10:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "67ec7c0706ec"
down_revision: Union[str, None] = "8daad1874818"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable column to port_definitions table
    # Default to False (required by default) to maintain existing behavior
    op.add_column(
        "port_definitions",
        sa.Column("nullable", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    # Remove nullable column from port_definitions table
    op.drop_column("port_definitions", "nullable")
