"""placeholder migration for missing revision

Revision ID: d0d10b5a7983
Revises: ed8f19491923
Create Date: 2025-10-13 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0d10b5a7983'
down_revision: Union[str, None] = '8cc2f22a492e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This is a placeholder migration to fix missing revision
    pass


def downgrade() -> None:
    # This is a placeholder migration to fix missing revision
    pass