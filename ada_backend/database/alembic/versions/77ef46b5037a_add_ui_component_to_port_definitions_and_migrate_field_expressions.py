"""add ui_component to port_definitions and migrate field_expressions to use port_definition_id

Revision ID: 77ef46b5037a
Revises: a4576629806f
Create Date: 2025-01-27 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from ada_backend.database.utils import create_enum_if_not_exists

# revision identifiers, used by Alembic.
revision: str = "77ef46b5037a"
down_revision: Union[str, None] = "a4576629806f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure ui_component enum exists (it should already exist from ComponentParameterDefinition)
    create_enum_if_not_exists(
        connection=op.get_bind(),
        enum_values=[
            "Autocomplete",
            "Checkbox",
            "Combobox",
            "Date Time Picker",
            "Editors",
            "File Input",
            "Radio",
            "Custom Input",
            "Range Slider",
            "Rating",
            "Select",
            "Slider",
            "Switch",
            "Textarea",
            "Textfield",
            "FileUpload",
            "JSON Builder",
        ],
        enum_name="ui_component",
    )

    ui_component_enum = postgresql.ENUM(
        "Autocomplete",
        "Checkbox",
        "Combobox",
        "Date Time Picker",
        "Editors",
        "File Input",
        "Radio",
        "Custom Input",
        "Range Slider",
        "Rating",
        "Select",
        "Slider",
        "Switch",
        "Textarea",
        "Textfield",
        "FileUpload",
        "JSON Builder",
        name="ui_component",
        create_type=False,
    )

    op.add_column(
        "port_definitions",
        sa.Column("ui_component", ui_component_enum, nullable=True),
    )
    op.add_column(
        "port_definitions",
        sa.Column("ui_component_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "port_definitions",
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column(
        "field_expressions",
        sa.Column("port_definition_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "field_expressions_port_definition_id_fkey",
        "field_expressions",
        "port_definitions",
        ["port_definition_id"],
        ["id"],
        ondelete="CASCADE",
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
        UPDATE field_expressions fe
        SET port_definition_id = (
            SELECT pd.id
            FROM port_definitions pd
            JOIN component_instances ci ON ci.component_version_id = pd.component_version_id
            WHERE ci.id = fe.component_instance_id
              AND pd.name = fe.field_name
              AND pd.port_type::text = 'INPUT'
            LIMIT 1
        )
        WHERE fe.port_definition_id IS NULL
    """
        )
    )

    # Delete any orphaned field_expressions that couldn't be matched
    # These are invalid records that reference non-existent ports
    connection.execute(
        sa.text(
            """
        DELETE FROM field_expressions
        WHERE port_definition_id IS NULL
    """
        )
    )

    op.alter_column("field_expressions", "port_definition_id", nullable=False)
    op.create_index(
        op.f("ix_field_expressions_port_definition_id"),
        "field_expressions",
        ["port_definition_id"],
        unique=False,
        if_not_exists=True,
    )

    op.drop_constraint("uq_field_expression_instance_field", "field_expressions", type_="unique")
    op.create_unique_constraint(
        "uq_field_expression_instance_port", "field_expressions", ["component_instance_id", "port_definition_id"]
    )
    op.drop_column("field_expressions", "field_name")

    op.add_column(
        "component_parameter_definitions",
        sa.Column("deprecated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "component_parameter_definitions",
        sa.Column("deprecation_message", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.add_column("field_expressions", sa.Column("field_name", sa.String(), nullable=True))
    op.drop_constraint("uq_field_expression_instance_port", "field_expressions", type_="unique")
    op.create_unique_constraint(
        "uq_field_expression_instance_field", "field_expressions", ["component_instance_id", "field_name"]
    )
    op.drop_index(
        op.f("ix_field_expressions_port_definition_id"),
        table_name="field_expressions",
        if_exists=True,
    )
    op.drop_constraint("field_expressions_port_definition_id_fkey", "field_expressions", type_="foreignkey")
    op.drop_column("field_expressions", "port_definition_id")

    op.drop_column("port_definitions", "is_optional")
    op.drop_column("port_definitions", "ui_component_properties")
    op.drop_column("port_definitions", "ui_component")

    op.drop_column("component_parameter_definitions", "deprecation_message")
    op.drop_column("component_parameter_definitions", "deprecated")
