"""Add port_instances base table and output_port_instances with polymorphic hierarchy

Revision ID: d0e1f2a3b4c5
Revises: a8b9c0d1e2f3
Create Date: 2026-02-25

Introduces:
- port_instances: shared base table for input/output port instances (joined-table polymorphism)
- output_port_instances: new child table for dynamic output ports driven by drives_output_schema inputs
- Migrates existing input_port_instances rows into the new hierarchy (base + child split)
- Adds source_output_port_instance_id to port_mappings for dynamic-source wiring
- Makes source_port_definition_id on port_mappings nullable (dynamic sources have no static definition)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reuse the existing port_type PostgreSQL enum (already has INPUT/OUTPUT values)
_port_type_enum = postgresql.ENUM("INPUT", "OUTPUT", name="port_type", create_type=False)


def upgrade() -> None:
    connection = op.get_bind()

    # 1. Create port_instances base table (reuses the existing port_type enum)
    op.create_table(
        "port_instances",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_instance_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("port_definition_id", sa.UUID(), nullable=True),
        sa.Column("type", _port_type_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(
            ["component_instance_id"],
            ["component_instances.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["port_definition_id"],
            ["port_definitions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("component_instance_id", "name", name="uq_port_instance_name"),
    )
    op.create_index(
        op.f("ix_port_instances_component_instance_id"),
        "port_instances",
        ["component_instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_port_instances_port_definition_id"),
        "port_instances",
        ["port_definition_id"],
        unique=False,
    )

    # 2. Migrate existing input_port_instances data into port_instances (type='INPUT')
    connection.execute(
        sa.text("""
            INSERT INTO port_instances (id, component_instance_id, name, port_definition_id, type, created_at)
            SELECT id, component_instance_id, name, port_definition_id, 'INPUT'::port_type, created_at
            FROM input_port_instances
        """)
    )

    # 3. Drop old unique constraint and indexes from input_port_instances before altering
    op.drop_constraint("uq_input_port_instance_name", "input_port_instances", type_="unique")
    op.drop_index(
        op.f("ix_input_port_instances_component_instance_id"),
        table_name="input_port_instances",
    )
    op.drop_index(
        op.f("ix_input_port_instances_port_definition_id"),
        table_name="input_port_instances",
    )

    # 4. Drop FK constraints on the columns we're removing from input_port_instances
    op.drop_constraint(
        "input_port_instances_component_instance_id_fkey",
        "input_port_instances",
        type_="foreignkey",
    )
    op.drop_constraint(
        "input_port_instances_port_definition_id_fkey",
        "input_port_instances",
        type_="foreignkey",
    )

    # 5. Add FK from input_port_instances.id to port_instances.id
    op.create_foreign_key(
        "input_port_instances_id_fkey",
        "input_port_instances",
        "port_instances",
        ["id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 6. Drop columns that moved to the base port_instances table
    op.drop_column("input_port_instances", "component_instance_id")
    op.drop_column("input_port_instances", "name")
    op.drop_column("input_port_instances", "port_definition_id")
    op.drop_column("input_port_instances", "created_at")

    # 7. Create output_port_instances child table
    op.create_table(
        "output_port_instances",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["port_instances.id"],
            name="output_port_instances_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 8. Add source_output_port_instance_id to port_mappings (nullable FK to port_instances)
    op.add_column(
        "port_mappings",
        sa.Column("source_output_port_instance_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_port_mappings_source_output_port_instance_id"),
        "port_mappings",
        ["source_output_port_instance_id"],
        unique=False,
    )
    op.create_foreign_key(
        "port_mappings_source_output_port_instance_id_fkey",
        "port_mappings",
        "port_instances",
        ["source_output_port_instance_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 9. Make source_port_definition_id on port_mappings nullable
    op.alter_column(
        "port_mappings",
        "source_port_definition_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    connection = op.get_bind()

    # Reverse: make source_port_definition_id non-nullable again
    # (rows with source_output_port_instance_id set must be removed first)
    connection.execute(
        sa.text("DELETE FROM port_mappings WHERE source_port_definition_id IS NULL")
    )
    op.alter_column(
        "port_mappings",
        "source_port_definition_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    # Remove source_output_port_instance_id from port_mappings
    op.drop_constraint(
        "port_mappings_source_output_port_instance_id_fkey",
        "port_mappings",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_port_mappings_source_output_port_instance_id"),
        table_name="port_mappings",
    )
    op.drop_column("port_mappings", "source_output_port_instance_id")

    # Drop output_port_instances
    op.drop_table("output_port_instances")

    # Restore input_port_instances: re-add the columns from port_instances
    op.add_column(
        "input_port_instances",
        sa.Column("component_instance_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "input_port_instances",
        sa.Column("name", sa.String(), nullable=True),
    )
    op.add_column(
        "input_port_instances",
        sa.Column("port_definition_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "input_port_instances",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )

    # Back-fill from port_instances
    connection.execute(
        sa.text("""
            UPDATE input_port_instances ipi
            SET component_instance_id = pi.component_instance_id,
                name = pi.name,
                port_definition_id = pi.port_definition_id,
                created_at = pi.created_at
            FROM port_instances pi
            WHERE ipi.id = pi.id
        """)
    )

    # Make component_instance_id non-nullable after back-fill
    op.alter_column("input_port_instances", "component_instance_id", nullable=False)
    op.alter_column("input_port_instances", "name", nullable=False)

    # Drop the FK added during upgrade
    op.drop_constraint("input_port_instances_id_fkey", "input_port_instances", type_="foreignkey")

    # Restore original FK constraints and indexes
    op.create_foreign_key(
        "input_port_instances_component_instance_id_fkey",
        "input_port_instances",
        "component_instances",
        ["component_instance_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "input_port_instances_port_definition_id_fkey",
        "input_port_instances",
        "port_definitions",
        ["port_definition_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_input_port_instances_component_instance_id"),
        "input_port_instances",
        ["component_instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_input_port_instances_port_definition_id"),
        "input_port_instances",
        ["port_definition_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_input_port_instance_name",
        "input_port_instances",
        ["component_instance_id", "name"],
    )

    # Drop port_instances base table (port_type enum is shared with port_definitions, do not drop it)
    op.drop_index(op.f("ix_port_instances_port_definition_id"), table_name="port_instances")
    op.drop_index(op.f("ix_port_instances_component_instance_id"), table_name="port_instances")
    op.drop_table("port_instances")
