"""add_json_schema_parameter_type

Revision ID: 6a2fe475860e
Revises: 2326e3fdacaa
Create Date: 2025-10-16 18:54:13.048806

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "6a2fe475860e"
down_revision: Union[str, None] = "2326e3fdacaa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE parameter_type ADD VALUE IF NOT EXISTS 'json_schema'")
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'Schema Builder'")


def downgrade() -> None:
    pass
