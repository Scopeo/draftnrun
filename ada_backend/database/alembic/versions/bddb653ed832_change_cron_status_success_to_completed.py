"""change_cron_status_success_to_completed

Revision ID: bddb653ed832
Revises: a4576629806f
Create Date: 2025-11-17 16:29:22.144702

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "bddb653ed832"
down_revision: Union[str, None] = "a4576629806f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'completed' to the enum type
    # PostgreSQL requires enum value additions to be committed before they can be used
    # We need to use the raw psycopg2 connection to commit separately from Alembic's transaction
    bind = op.get_bind()
    # Get the raw psycopg2 connection
    raw_conn = bind.connection.dbapi_connection
    # Execute the ALTER TYPE command directly on the raw connection
    with raw_conn.cursor() as cursor:
        cursor.execute("ALTER TYPE scheduler.cron_status ADD VALUE IF NOT EXISTS 'completed'")
    # Commit on the raw connection (this commits outside of Alembic's transaction)
    raw_conn.commit()

    # Update all existing 'success' values to 'completed'
    # This can now use the new enum value since it was committed above
    op.execute(
        """
        UPDATE scheduler.cron_runs
        SET status = 'completed'::scheduler.cron_status
        WHERE status = 'success'::scheduler.cron_status;
    """
    )

    # Note: We cannot directly remove 'success' from the enum type in PostgreSQL
    # The enum value will remain but won't be used by new code
    # To fully remove it, we would need to recreate the enum type, which is more complex


def downgrade() -> None:
    # Update all 'completed' values back to 'success'
    op.execute(
        """
        UPDATE scheduler.cron_runs
        SET status = 'success'::scheduler.cron_status
        WHERE status = 'completed'::scheduler.cron_status;
    """
    )

    # Note: 'completed' will remain in the enum type
    # PostgreSQL doesn't support removing enum values directly
