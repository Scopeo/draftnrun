"""add cron to CallType and queued to cron_status

Revision ID: 4071a252013a
Revises: a2b3c4d5e6f7
Create Date: 2026-03-10 11:03:38.203036

"""

from typing import Sequence, Union

from alembic import op

revision: str = "4071a252013a"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE call_type ADD VALUE IF NOT EXISTS 'cron'")
        op.execute("ALTER TYPE scheduler.cron_status ADD VALUE IF NOT EXISTS 'queued'")


def downgrade() -> None:
    pass
