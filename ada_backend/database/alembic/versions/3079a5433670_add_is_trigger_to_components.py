"""add is_trigger to components

Revision ID: 3079a5433670
Revises: dwh7zeh4dibz
Create Date: 2026-03-11 13:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3079a5433670"
down_revision: Union[str, None] = "dwh7zeh4dibz"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "components",
        sa.Column("is_trigger", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("components", "is_trigger")
