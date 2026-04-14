"""add project_alert_emails table

Revision ID: a1b2c3d4f6g8
Revises: 4071a252013a
Create Date: 2026-04-14 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "a1b2c3d4f6g8"
down_revision: Union[str, None] = "4071a252013a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"


def upgrade() -> None:
    op.create_table(
        "project_alert_emails",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "email", name="uq_project_alert_email"),
    )
    op.create_index("ix_project_alert_emails_project_id", "project_alert_emails", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_alert_emails_project_id", table_name="project_alert_emails")
    op.drop_table("project_alert_emails")
