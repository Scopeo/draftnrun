"""change embedding_model_name to embedding_model_referance

Revision ID: 80118747a315
Revises: 2301736f9201
Create Date: 2025-06-24 12:35:43.167536

"""
from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '80118747a315'
down_revision: Union[str, None] = '2301736f9201'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename column without losing data
    op.alter_column('data_sources', 'embedding_model_name', new_column_name='embedding_model_referance')


def downgrade() -> None:
    # Revert to original column name
    op.alter_column('data_sources', 'embedding_model_referance', new_column_name='embedding_model_name')
