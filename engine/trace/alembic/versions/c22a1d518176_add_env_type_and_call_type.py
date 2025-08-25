"""add env_type and call_type

Revision ID: c22a1d518176
Revises: f6dfd93b8baf
Create Date: 2025-08-25 11:32:08.506288

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c22a1d518176"
down_revision: Union[str, None] = "f6dfd93b8baf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enum types first
    env_type_enum = sa.Enum("draft", "production", name="env_type")
    call_type_enum = sa.Enum("api", "sandbox", name="call_type")

    # Explicitly create the enum types in the database
    env_type_enum.create(op.get_bind(), checkfirst=True)
    call_type_enum.create(op.get_bind(), checkfirst=True)

    # Add the columns using the created enum types
    op.add_column("spans", sa.Column("environment", env_type_enum, nullable=True))
    op.add_column("spans", sa.Column("call_type", call_type_enum, nullable=True))

    # Create indexes for better query performance
    op.create_index(op.f("ix_spans_environment"), "spans", ["environment"], unique=False)
    op.create_index(op.f("ix_spans_call_type"), "spans", ["call_type"], unique=False)


def downgrade() -> None:
    # Drop the indexes first
    op.drop_index(op.f("ix_spans_call_type"), table_name="spans")
    op.drop_index(op.f("ix_spans_environment"), table_name="spans")

    # Drop the columns
    op.drop_column("spans", "call_type")
    op.drop_column("spans", "environment")

    # Drop the enum types
    sa.Enum(name="call_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="env_type").drop(op.get_bind(), checkfirst=True)
