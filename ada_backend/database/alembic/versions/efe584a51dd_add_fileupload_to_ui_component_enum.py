"""add fileupload to ui_component enum

Revision ID: efe584a51dd
Revises: 5154754574cb
Create Date: 2025-01-27 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "efe584a51dd"
down_revision: Union[str, None] = "5154754574cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'FileUpload' value to the ui_component enum
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'FileUpload'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The 'FileUpload' value will remain in the enum type even after downgrade.
    # This is harmless and won't affect the application.
    pass
