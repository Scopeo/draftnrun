"""Add port definitions and mappings tables

Revision ID: f94e9fdc03e4
Revises: 79e3872b3b03
Create Date: 2025-09-24 03:55:39.848809

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from ada_backend.database.utils import create_enum_if_not_exists, drop_enum_if_exists


# revision identifiers, used by Alembic.
revision: str = "f94e9fdc03e4"
down_revision: Union[str, None] = "8ae8246c0768"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    create_enum_if_not_exists(
        connection=op.get_bind(),
        enum_values=["INPUT", "OUTPUT"],
        enum_name="port_type",
    )

    port_type_enum = postgresql.ENUM("INPUT", "OUTPUT", name="port_type", create_type=False)

    op.create_table(
        "port_definitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("port_type", port_type_enum, nullable=False),
        sa.Column("is_canonical", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "port_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("graph_runner_id", sa.UUID(), nullable=False),
        sa.Column("source_instance_id", sa.UUID(), nullable=False),
        sa.Column("source_port_definition_id", sa.UUID(), nullable=False),
        sa.Column("target_instance_id", sa.UUID(), nullable=False),
        sa.Column("target_port_definition_id", sa.UUID(), nullable=False),
        sa.Column("dispatch_strategy", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["graph_runner_id"], ["graph_runners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_instance_id"], ["component_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_instance_id"], ["component_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_port_definition_id"], ["port_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_port_definition_id"], ["port_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add unique constraint to port_definitions
    op.create_unique_constraint("unique_component_port", "port_definitions", ["component_id", "name", "port_type"])


def downgrade() -> None:
    op.drop_table("port_mappings")
    op.drop_table("port_definitions")
    drop_enum_if_exists(
        connection=op.get_bind(),
        enum_name="port_type",
    )
