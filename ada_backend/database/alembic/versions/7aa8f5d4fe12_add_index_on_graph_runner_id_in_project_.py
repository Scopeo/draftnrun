"""Add index on graph_runner_id in project_env_binding

Revision ID: 7aa8f5d4fe12
Revises: c4745d51078c
Create Date: 2026-01-19 18:22:26.051992

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7aa8f5d4fe12'
down_revision: Union[str, None] = 'c4745d51078c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_project_env_binding_graph_runner_id',
        'project_env_binding',
        ['graph_runner_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_project_env_binding_graph_runner_id', table_name='project_env_binding')
