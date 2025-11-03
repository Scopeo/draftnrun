"""add endpoint_id_tracker to cron_entrypoint

Revision ID: b1c2d3e4f5a6
Revises: a86270305bab
Create Date: 2025-01-20 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a86270305bab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'endpoint_id_tracker' to the existing cron_entrypoint enum
    op.execute(
        """
        ALTER TYPE scheduler.cron_entrypoint ADD VALUE IF NOT EXISTS 'endpoint_id_tracker';
        """
    )


def downgrade() -> None:
    # Note: PostgreSQL does not support removing enum values directly
    # This would require recreating the enum type, which is complex
    # For now, we'll leave a comment about this limitation
    # In practice, you would need to:
    # 1. Create a new enum without the value
    # 2. Update all columns using the old enum
    # 3. Drop the old enum
    # 4. Rename the new enum
    # This is a destructive operation and should be done carefully
    op.execute(
        """
        -- Cannot remove enum value directly in PostgreSQL
        -- Manual intervention required if downgrade is necessary
        -- Comment kept for reference
        """
    )
