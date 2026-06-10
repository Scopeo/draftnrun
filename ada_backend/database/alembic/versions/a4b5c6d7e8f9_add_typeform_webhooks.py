"""add typeform webhooks

Revision ID: a4b5c6d7e8f9
Revises: 9b1f8e3a4c2d
Create Date: 2026-06-10 10:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "9b1f8e3a4c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
deploy_strategy = "migrate-first"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE webhook_provider ADD VALUE IF NOT EXISTS 'typeform'")

    op.add_column("webhooks", sa.Column("encrypted_signing_secret", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("webhooks", "encrypted_signing_secret")
