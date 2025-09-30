"""add tag_version

Revision ID: c4814af70804
Revises: c22a1d518176
Create Date: 2025-09-22 11:04:58.582117

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4814af70804"
down_revision: Union[str, None] = "40f09397fc95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.add_column("spans", sa.Column("tag_version", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("spans", "tag_version")
