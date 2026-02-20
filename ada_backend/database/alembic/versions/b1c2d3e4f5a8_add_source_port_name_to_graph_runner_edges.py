"""add source_port_name to graph_runner_edges

Revision ID: b1c2d3e4f5a8
Revises: a1b2c3d4e5f7
Create Date: 2026-02-19 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a8"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add source_port_name column to graph_runner_edges
    op.add_column('graph_runner_edges', sa.Column('source_port_name', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove source_port_name column from graph_runner_edges
    op.drop_column('graph_runner_edges', 'source_port_name')
