"""add endpoint_polling to cron_entrypoint

Revision ID: b1c2d3e4f5a6
Revises: a86270305bab
Create Date: 2025-01-20 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "5154754574cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TYPE scheduler.cron_entrypoint ADD VALUE IF NOT EXISTS 'endpoint_polling';
        """
    )
    op.create_table(
        "endpoint_polling_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cron_id", sa.UUID(), nullable=False),
        sa.Column("tracked_value", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["cron_id"],
            ["scheduler.cron_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cron_id", "tracked_value", name="uq_cron_tracked_value"),
        schema="scheduler",
    )
    op.create_index(
        op.f("ix_endpoint_polling_history_id"),
        "endpoint_polling_history",
        ["id"],
        unique=False,
        schema="scheduler",
    )
    op.create_index(
        op.f("ix_endpoint_polling_history_cron_id"),
        "endpoint_polling_history",
        ["cron_id"],
        unique=False,
        schema="scheduler",
    )
    op.create_index(
        op.f("ix_endpoint_polling_history_tracked_value"),
        "endpoint_polling_history",
        ["tracked_value"],
        unique=False,
        schema="scheduler",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_endpoint_polling_history_tracked_value"), table_name="endpoint_polling_history", schema="scheduler"
    )
    op.drop_index(
        op.f("ix_endpoint_polling_history_cron_id"), table_name="endpoint_polling_history", schema="scheduler"
    )
    op.drop_index(op.f("ix_endpoint_polling_history_id"), table_name="endpoint_polling_history", schema="scheduler")
    op.drop_table("endpoint_polling_history", schema="scheduler")
