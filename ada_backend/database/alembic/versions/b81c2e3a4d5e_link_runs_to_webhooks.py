"""link_runs_to_webhooks

Revision ID: b81c2e3a4d5e
Revises: a3b4c5d6e7f8
Create Date: 2026-03-09 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b81c2e3a4d5e"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("webhook_id", sa.UUID(), nullable=True))
    op.add_column("runs", sa.Column("integration_trigger_id", sa.UUID(), nullable=True))

    op.create_foreign_key(
        "fk_runs_webhook_id_webhooks",
        "runs",
        "webhooks",
        ["webhook_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_runs_integration_trigger_id_integration_triggers",
        "runs",
        "integration_triggers",
        ["integration_trigger_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(op.f("ix_runs_webhook_id"), "runs", ["webhook_id"], unique=False)
    op.create_index(op.f("ix_runs_integration_trigger_id"), "runs", ["integration_trigger_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_runs_integration_trigger_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_webhook_id"), table_name="runs")

    op.drop_constraint("fk_runs_integration_trigger_id_integration_triggers", "runs", type_="foreignkey")
    op.drop_constraint("fk_runs_webhook_id_webhooks", "runs", type_="foreignkey")

    op.drop_column("runs", "integration_trigger_id")
    op.drop_column("runs", "webhook_id")
