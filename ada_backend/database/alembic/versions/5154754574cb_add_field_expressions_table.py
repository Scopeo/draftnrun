"""add field_expressions table

Revision ID: 5154754574cb
Revises: a86270305bab
Create Date: 2025-10-23 13:44:32.912392

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5154754574cb"
down_revision: Union[str, None] = "a86270305bab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "field_expressions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_instance_id", sa.UUID(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("expression_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["component_instance_id"], ["component_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("component_instance_id", "field_name", name="uq_field_expression_instance_field"),
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_field_expressions_component_instance_id"),
        "field_expressions",
        ["component_instance_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_field_expressions_id"),
        "field_expressions",
        ["id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_field_expressions_id"),
        table_name="field_expressions",
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_field_expressions_component_instance_id"),
        table_name="field_expressions",
        if_exists=True,
    )
    op.drop_table("field_expressions", if_exists=True)
