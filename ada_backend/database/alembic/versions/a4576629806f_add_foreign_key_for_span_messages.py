"""add_foreign_key_for_span_messages

Revision ID: a4576629806f
Revises: 88dcf82ab86
Create Date: 2025-10-21 13:08:54.099132

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a4576629806f"
down_revision: Union[str, None] = "88dcf82ab86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clean up orphaned span_messages records
    op.execute(
        """
        DELETE FROM traces.span_messages
        WHERE span_id NOT IN (SELECT span_id FROM traces.spans)
    """
    )

    # Add foreign key constraint to span_messages table
    op.execute(
        """
        ALTER TABLE traces.span_messages
        ADD CONSTRAINT span_messages_span_id_fkey
        FOREIGN KEY (span_id) REFERENCES traces.spans(span_id) ON DELETE CASCADE
    """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE traces.span_messages DROP CONSTRAINT IF EXISTS span_messages_span_id_fkey")
