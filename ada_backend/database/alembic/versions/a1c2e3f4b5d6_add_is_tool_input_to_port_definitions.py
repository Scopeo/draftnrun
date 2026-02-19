"""add is_tool_input to port definitions

Revision ID: a1c2e3f4b5d6
Revises: f3a1b2c4d5e6
Create Date: 2026-02-19 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c2e3f4b5d6"
down_revision: Union[str, None] = "f3a1b2c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "port_definitions",
        sa.Column("is_tool_input", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("port_definitions", "is_tool_input")
