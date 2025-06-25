"""change embedding_model_name to embedding_model_reference

Revision ID: 80118747a315
Revises: 2301736f9201
Create Date: 2025-06-24 12:35:43.167536
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "80118747a315"
down_revision: Union[str, None] = "2301736f9201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename column
    op.alter_column("data_sources", "embedding_model_name", new_column_name="embedding_model_reference")

    # Update values in the renamed column
    op.execute(
        """
        UPDATE data_sources
        SET embedding_model_reference = 'openai:text-embedding-3-large'
        WHERE embedding_model_reference = 'text-embedding-3-large'
        """
    )
    op.execute(
        """
        UPDATE basic_parameters
        SET value = 'openai:gpt-4.1-mini'
        WHERE value IN ('openai:o4-mini-2025-04-16', 'openai:o3-2025-04-16')
        """
    )


def downgrade() -> None:
    # Revert value change before renaming back
    op.execute(
        """
        UPDATE data_sources
        SET embedding_model_reference = 'text-embedding-3-large'
        WHERE embedding_model_reference = 'openai:text-embedding-3-large'
        """
    )
    op.execute(
        """
        UPDATE basic_parameters
        SET value = 'openai:o4-mini-2025-04-16'
        WHERE value = 'openai:gpt-4.1-mini'
        """
    )

    # Rename column back
    op.alter_column("data_sources", "embedding_model_reference", new_column_name="embedding_model_name")
