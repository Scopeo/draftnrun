"""add field_formulas table

Revision ID: 5154754574cb
Revises: f1e79aa97806
Create Date: 2025-10-23 13:44:32.912392

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5154754574cb"
down_revision: Union[str, None] = "f1e79aa97806"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "field_formulas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_instance_id", sa.UUID(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("formula_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["component_instance_id"], ["component_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("component_instance_id", "field_name", name="uq_field_expr_instance_field"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_field_formulas_component_instance_id"),
        "field_formulas",
        ["component_instance_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_field_formulas_id"),
        "field_formulas",
        ["id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_field_formulas_id"),
        table_name="field_formulas",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_field_formulas_component_instance_id"),
        table_name="field_formulas",
        if_exists=True,
    )
    op.drop_table("field_formulas", if_exists=True)
