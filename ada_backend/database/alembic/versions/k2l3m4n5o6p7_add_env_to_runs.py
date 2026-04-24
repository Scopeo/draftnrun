"""add_env_to_runs

Revision ID: k2l3m4n5o6p7
Revises: 67df5c87b638
Create Date: 2026-04-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "k2l3m4n5o6p7"
down_revision: Union[str, None] = "67df5c87b638"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

env_type_enum = postgresql.ENUM("draft", "production", name="env_type", create_type=False)


def upgrade() -> None:
    op.add_column("runs", sa.Column("env", env_type_enum, nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "env")
