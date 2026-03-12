"""add tool input configurations table

Revision ID: a1b2c3d4e5f8
Revises: b81c2e3a4d5e
Create Date: 2026-01-30 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ada_backend.database.utils import create_enum_if_not_exists, drop_enum_if_exists

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f8"
down_revision: Union[str, None] = "b81c2e3a4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Port setup mode enum
    enum_values = ["user_set", "deactivated", "ai_filled"]
    create_enum_if_not_exists(bind, enum_values=enum_values, enum_name="port_setup_mode")
    port_setup_mode_enum = postgresql.ENUM(name="port_setup_mode", create_type=False)

    # JSON Schema type enum (for LLM tool schemas)
    json_schema_type_values = ["string", "integer", "number", "boolean", "object", "array"]
    create_enum_if_not_exists(bind, enum_values=json_schema_type_values, enum_name="json_schema_type")
    json_schema_type_enum = postgresql.ENUM(name="json_schema_type", create_type=False)

    # Create tool_input_configurations as a standalone table referencing InputPortInstance.
    # Each InputPortInstance can have at most one ToolInputConfiguration (UNIQUE constraint).
    # This table stores LLM tool-schema metadata only; the port value (field_expression_id)
    # lives on input_port_instances.
    op.create_table(
        "tool_input_configurations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("input_port_instance_id", sa.UUID(), nullable=False),
        sa.Column("setup_mode", port_setup_mode_enum, nullable=False),
        # LLM schema overrides
        sa.Column("ai_name_override", sa.String(), nullable=True),
        sa.Column("ai_description_override", sa.Text(), nullable=True),
        sa.Column(
            "is_required_override",
            sa.Boolean(),
            nullable=True,
            comment="Override required status: True=mandatory, False=optional, None=use port definition default",
        ),
        # For dynamic ports without a PortDefinition: the JSON Schema type
        sa.Column("custom_parameter_type", json_schema_type_enum, nullable=True),
        # Full JSON Schema override for complex parameter types
        sa.Column(
            "json_schema_override",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Full JSON Schema for complex parameter types. Overrides simple type mapping.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["input_port_instance_id"],
            ["input_port_instances.id"],
            name="fk_tool_input_configurations_input_port_instance_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("input_port_instance_id", name="uq_tool_input_configurations_input_port_instance_id"),
    )

    op.create_index(
        "ix_tool_input_configurations_input_port_instance_id",
        "tool_input_configurations",
        ["input_port_instance_id"],
    )

    # Add nullable column to port_definitions (True = optional port, False = required)
    op.add_column(
        "port_definitions",
        sa.Column(
            "nullable",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="True if port is optional, False if required",
        ),
    )

    # Populate port_definitions.nullable from the corresponding component_parameter_definitions
    op.execute("""
        UPDATE port_definitions pd
        SET nullable = COALESCE(
            (
                SELECT cpd.nullable
                FROM component_parameter_definitions cpd
                WHERE cpd.component_version_id = pd.component_version_id
                  AND cpd.name = pd.name
                LIMIT 1
            ),
            true
        )
    """)

    # DATA MIGRATION: for component_instances that already have tool_descriptions and whose
    # ports are already materialised as input_port_instances, create ToolInputConfiguration
    # rows so the new system is populated for existing data.
    op.execute("""
        WITH effective_tool_descriptions AS (
            SELECT
                ci.id AS component_instance_id,
                ci.component_version_id,
                COALESCE(ci.tool_description_id, cv.default_tool_description_id) AS tool_description_id
            FROM component_instances ci
            INNER JOIN component_versions cv ON ci.component_version_id = cv.id
            WHERE COALESCE(ci.tool_description_id, cv.default_tool_description_id) IS NOT NULL
        )
        INSERT INTO tool_input_configurations (
            id,
            input_port_instance_id,
            setup_mode,
            ai_name_override,
            ai_description_override,
            is_required_override,
            custom_parameter_type,
            json_schema_override,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid()                          AS id,
            ipi.id                                     AS input_port_instance_id,
            'ai_filled'::port_setup_mode               AS setup_mode,
            NULL                                       AS ai_name_override,
            CASE
                WHEN (td.tool_properties::jsonb -> pd.name ->> 'description') IS NOT NULL
                     AND (td.tool_properties::jsonb -> pd.name ->> 'description') IS DISTINCT FROM pd.description
                THEN (td.tool_properties::jsonb -> pd.name ->> 'description')
                ELSE NULL
            END                                        AS ai_description_override,
            CASE
                WHEN (td.required_tool_properties::jsonb ? pd.name) AND pd.nullable = true
                THEN true
                ELSE NULL
            END                                        AS is_required_override,
            NULL                                       AS custom_parameter_type,
            CASE
                WHEN td.tool_properties::jsonb -> pd.name ? 'items'
                    OR td.tool_properties::jsonb -> pd.name ? 'properties'
                    OR td.tool_properties::jsonb -> pd.name ? 'enum'
                    OR td.tool_properties::jsonb -> pd.name ? 'oneOf'
                    OR td.tool_properties::jsonb -> pd.name ? 'anyOf'
                    OR td.tool_properties::jsonb -> pd.name ? 'allOf'
                    OR (td.tool_properties::jsonb -> pd.name ->> 'type') IN ('array', 'object')
                THEN td.tool_properties::jsonb -> pd.name
                ELSE NULL
            END                                        AS json_schema_override,
            NOW()                                      AS created_at,
            NOW()                                      AS updated_at
        FROM effective_tool_descriptions etd
        INNER JOIN tool_descriptions td ON etd.tool_description_id = td.id
        INNER JOIN port_instances pi
            ON pi.component_instance_id = etd.component_instance_id
            AND pi.type = 'INPUT'
        INNER JOIN input_port_instances ipi ON ipi.id = pi.id
        INNER JOIN port_definitions pd ON pd.id = pi.port_definition_id
        WHERE EXISTS (
            SELECT 1
            FROM jsonb_object_keys(td.tool_properties::jsonb) AS prop_key
            WHERE prop_key = pd.name
        )
        ON CONFLICT (input_port_instance_id) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_index("ix_tool_input_configurations_input_port_instance_id", table_name="tool_input_configurations")
    op.drop_table("tool_input_configurations")

    drop_enum_if_exists(connection=op.get_bind(), enum_name="port_setup_mode")
    drop_enum_if_exists(connection=op.get_bind(), enum_name="json_schema_type")

    op.drop_column("port_definitions", "nullable")
