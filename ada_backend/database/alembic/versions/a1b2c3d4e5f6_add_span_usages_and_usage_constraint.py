"""add span_usages table and usage constraint

Revision ID: a1b2c3d4e5f6
Revises: 6deaee79f30a
Create Date: 2025-12-01 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "6deaee79f30a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create span_usages table in credits schema
    op.create_table(
        "span_usages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("credits_input_token", sa.Float(), nullable=True),
        sa.Column("credits_output_token", sa.Float(), nullable=True),
        sa.Column("credits_per_call", sa.Float(), nullable=True),
        sa.Column("credits_per_second", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["span_id"],
            ["traces.spans.span_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="credits",
    )
    # Create unique index on span_id (matches model: unique=True, index=True)
    op.create_index(op.f("ix_credits_span_usages_span_id"), "span_usages", ["span_id"], unique=True, schema="credits")

    # Add unique constraint to usages table
    op.create_unique_constraint(
        "uq_usage_project_year_month",
        "usages",
        ["project_id", "year", "month"],
        schema="credits",
    )


def downgrade() -> None:
    # Drop unique constraint from usages
    op.drop_constraint("uq_usage_project_year_month", "usages", schema="credits", type_="unique")

    # Drop span_usages table (indexes are dropped automatically with table)
    op.drop_index(op.f("ix_credits_span_usages_span_id"), table_name="span_usages", schema="credits")
    op.drop_table("span_usages", schema="credits")
