"""add_apscheduler_jobs_table

Revision ID: add_apscheduler_jobs
Revises: 8100496c09e5
Create Date: 2025-01-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_apscheduler_jobs"
down_revision: Union[str, None] = "8100496c09e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create APScheduler jobs table
    op.create_table(
        "apscheduler_jobs",
        sa.Column("id", sa.Unicode(191), nullable=False),
        sa.Column("next_run_time", sa.Float(25), nullable=True),
        sa.Column("job_state", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_apscheduler_jobs_next_run_time", "next_run_time"),
    )


def downgrade() -> None:
    op.drop_table("apscheduler_jobs")
