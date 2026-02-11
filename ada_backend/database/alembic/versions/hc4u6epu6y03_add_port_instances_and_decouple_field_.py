"""add port instances and decouple field expressions

Revision ID: hc4u6epu6y03
Revises: 67ec7c0706ec
Create Date: 2026-02-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hc4u6epu6y03"
down_revision: Union[str, None] = "67ec7c0706ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create input_port_instances table
    op.create_table(
        "input_port_instances",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_instance_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("port_definition_id", sa.UUID(), nullable=True),
        sa.Column("field_expression_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["field_expression_id"],
            ["field_expressions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("component_instance_id", "name", name="uq_input_port_instance_name"),
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
    op.create_index(
        op.f("ix_input_port_instances_field_expression_id"),
        "input_port_instances",
        ["field_expression_id"],
        unique=False,
    )

    # Data migration: Convert existing field_expressions to input_port_instances
    # This needs to happen before we drop the old columns
    connection = op.get_bind()

    # Get all existing field expressions
    result = connection.execute(
        sa.text("""
            SELECT id, component_instance_id, field_name, expression_json, updated_at
            FROM field_expressions
        """)
    )

    old_field_expressions = result.fetchall()

    # For each old field expression, create a new one (without component_instance_id and field_name)
    # and an input_port_instance that links them
    for old_expr in old_field_expressions:
        old_id = old_expr[0]
        component_instance_id = old_expr[1]
        field_name = old_expr[2]
        expression_json = old_expr[3]
        updated_at = old_expr[4]

        # Create new field expression with just the expression_json
        # We'll reuse the same ID to maintain the reference
        # (We'll update the record in place after dropping columns)

        # Create input_port_instance linking to the existing field_expression
        connection.execute(
            sa.text("""
                INSERT INTO input_port_instances 
                    (id, component_instance_id, name, field_expression_id, created_at)
                VALUES 
                    (gen_random_uuid(), :component_instance_id, :field_name, :field_expression_id, now())
            """),
            {
                "component_instance_id": component_instance_id,
                "field_name": field_name,
                "field_expression_id": old_id,
            },
        )

    # Modify field_expressions table - remove component_instance_id relationship
    op.drop_constraint("uq_field_expression_instance_field", "field_expressions", type_="unique")
    op.drop_index("ix_field_expressions_component_instance_id", table_name="field_expressions")
    op.drop_constraint(
        "field_expressions_component_instance_id_fkey",
        "field_expressions",
        type_="foreignkey",
    )
    op.drop_column("field_expressions", "component_instance_id")
    op.drop_column("field_expressions", "field_name")


def downgrade() -> None:
    # Note: This is a breaking change. Downgrade will restore structure and migrate data back.

    # Restore field_expressions columns
    op.add_column(
        "field_expressions",
        sa.Column("field_name", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "field_expressions",
        sa.Column(
            "component_instance_id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("'00000000-0000-0000-0000-000000000000'"),
        ),
    )

    # Data migration: Restore data from input_port_instances to field_expressions
    connection = op.get_bind()

    # Get all input_port_instances with their field_expressions
    result = connection.execute(
        sa.text("""
            SELECT ipi.component_instance_id, ipi.name, ipi.field_expression_id
            FROM input_port_instances ipi
            WHERE ipi.field_expression_id IS NOT NULL
        """)
    )

    port_instances = result.fetchall()

    # Update field_expressions with component_instance_id and field_name
    for port_instance in port_instances:
        component_instance_id = port_instance[0]
        field_name = port_instance[1]
        field_expression_id = port_instance[2]

        connection.execute(
            sa.text("""
                UPDATE field_expressions
                SET component_instance_id = :component_instance_id,
                    field_name = :field_name
                WHERE id = :field_expression_id
            """),
            {
                "component_instance_id": component_instance_id,
                "field_name": field_name,
                "field_expression_id": field_expression_id,
            },
        )

    op.create_foreign_key(
        "field_expressions_component_instance_id_fkey",
        "field_expressions",
        "component_instances",
        ["component_instance_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_field_expressions_component_instance_id",
        "field_expressions",
        ["component_instance_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_field_expression_instance_field",
        "field_expressions",
        ["component_instance_id", "field_name"],
    )

    # Remove server defaults after constraint creation
    op.alter_column("field_expressions", "field_name", server_default=None)
    op.alter_column("field_expressions", "component_instance_id", server_default=None)

    # Drop input_port_instances table
    op.drop_index(op.f("ix_input_port_instances_field_expression_id"), table_name="input_port_instances")
    op.drop_index(op.f("ix_input_port_instances_port_definition_id"), table_name="input_port_instances")
    op.drop_index(op.f("ix_input_port_instances_component_instance_id"), table_name="input_port_instances")
    op.drop_table("input_port_instances")
