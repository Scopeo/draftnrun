"""add exclusive oauth connection ui component enum value

Revision ID: 88538199bc7b
Revises: 93189a98fdf2
Create Date: 2026-04-29 17:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "88538199bc7b"
down_revision: Union[str, None] = "93189a98fdf2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy: Union[str, None] = "migrate-first"


def upgrade() -> None:
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'ExclusiveOAuthConnection'")


def downgrade() -> None:
    pass
