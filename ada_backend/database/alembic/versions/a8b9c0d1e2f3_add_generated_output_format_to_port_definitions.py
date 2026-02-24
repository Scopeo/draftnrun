"""Add drives_output_schema to port definitions (input ports only)

Revision ID: a8b9c0d1e2f3
Revises: 6c3f812c5752
Create Date: 2026-02-24

For input ports only: when true, this input drives the output schema and effectively
adds a corresponding output port (e.g. output_format in AI Agent and LLM Call).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "6c3f812c5752"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "port_definitions",
        sa.Column("drives_output_schema", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("port_definitions", "drives_output_schema")
