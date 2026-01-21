"""add_project_icons

Revision ID: c4745d51078c
Revises: 475546bc2802
Create Date: 2026-01-16 18:37:08.264959

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4745d51078c'
down_revision: Union[str, None] = '475546bc2802'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('icon', sa.String(), nullable=True))
    op.add_column('projects', sa.Column('icon_color', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('projects', 'icon_color')
    op.drop_column('projects', 'icon')
