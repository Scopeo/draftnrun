"""add flag to components

Revision ID: 3ab342cef192
Revises: f35bfa8d86b7
Create Date: 2025-06-04 17:55:35.370577

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3ab342cef192"
down_revision: Union[str, None] = "f35bfa8d86b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    feature_flag_enum = sa.Enum("beta", "early_access", "public", "internal", name="release_stage")
    feature_flag_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "components", sa.Column("release_stage", feature_flag_enum, nullable=False, server_default="internal")
    )
    op.alter_column("components", "release_stage", server_default="internal")


def downgrade() -> None:
    op.drop_column("components", "release_stage")
    # Drop the ENUM type after removing the column
    sa.Enum(name="release_stage").drop(op.get_bind(), checkfirst=True)
