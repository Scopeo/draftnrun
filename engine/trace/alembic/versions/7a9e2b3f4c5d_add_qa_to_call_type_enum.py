"""add qa to call_type enum

Revision ID: 7a9e2b3f4c5d
Revises: c4814af70804
Create Date: 2025-10-09 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7a9e2b3f4c5d"
down_revision: Union[str, None] = "3ef4828f70f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'qa' value to the call_type enum
    op.execute("ALTER TYPE call_type ADD VALUE IF NOT EXISTS 'qa'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The 'qa' value will remain in the enum type even after downgrade.
    # This is harmless and won't affect the application.
    pass
