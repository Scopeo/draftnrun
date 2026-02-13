"""add port configurations table

Revision ID: a1b2c3d4e5f7
Revises: fe1c665d7821
Create Date: 2026-01-30 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ada_backend.database.utils import create_enum_if_not_exists, drop_enum_if_exists

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "fe1c665d7821"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the enums
    bind = op.get_bind()

    # Port setup mode enum
    enum_values = ["user_set", "deactivated", "ai_filled"]
    create_enum_if_not_exists(bind, enum_values=enum_values, enum_name="port_setup_mode")
    port_setup_mode_enum = postgresql.ENUM(name="port_setup_mode", create_type=False)

    # JSON Schema type enum (for LLM tool schemas)
    json_schema_type_values = ["string", "integer", "number", "boolean", "object", "array"]
    create_enum_if_not_exists(bind, enum_values=json_schema_type_values, enum_name="json_schema_type")
    json_schema_type_enum = postgresql.ENUM(name="json_schema_type", create_type=False)

    # Create the BASE port_configurations table (shared fields only)
    # NOTE: Port configurations should only be created for INPUT ports or custom ports (null port_definition_id)
    # OUTPUT ports should NOT have port configurations (enforced at both database and application level)
    op.create_table(
        "port_configurations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_instance_id", sa.UUID(), nullable=False),
        sa.Column("port_definition_id", sa.UUID(), nullable=True),
        sa.Column("field_expression_id", sa.UUID(), nullable=True),
        # Polymorphic discriminator
        sa.Column("config_type", sa.String(), nullable=False),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["component_instance_id"],
            ["component_instances.id"],
            name="fk_port_configurations_component_instance_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["port_definition_id"],
            ["port_definitions.id"],
            name="fk_port_configurations_port_definition_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["field_expression_id"],
            ["field_expressions.id"],
            name="fk_port_configurations_field_expression_id",
            ondelete="CASCADE",
        ),
    )

    # Create the CHILD tool_input_configurations table (tool-specific fields)
    op.create_table(
        "tool_input_configurations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("setup_mode", port_setup_mode_enum, nullable=False),
        sa.Column("ai_name_override", sa.String(), nullable=True),
        sa.Column("ai_description_override", sa.Text(), nullable=True),
        # is_required_override: True=make optional port mandatory, False/None=use default
        # Cannot make required ports optional
        sa.Column(
            "is_required_override",
            sa.Boolean(),
            nullable=True,
            comment="Override required status: True=mandatory, False=optional, None=use port definition default",
        ),
        # Custom port fields (when port_definition_id IS NULL)
        sa.Column("custom_port_name", sa.String(), nullable=True),
        sa.Column("custom_port_description", sa.Text(), nullable=True),
        sa.Column("custom_parameter_type", json_schema_type_enum, nullable=True),
        sa.Column("custom_ui_component_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Full JSON Schema override for complex parameter types
        sa.Column(
            "json_schema_override",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Full JSON Schema for complex parameter types. Overrides simple type mapping.",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["id"],
            ["port_configurations.id"],
            name="fk_tool_input_configurations_id",
            ondelete="CASCADE",
        ),
        # Check constraint: port_definition_id IS NULL (in parent) implies custom_port_name IS NOT NULL
        # Note: This will be enforced at application level since we can't easily reference parent table
    )

    # Create index for queries by component_instance_id
    op.create_index(
        "ix_port_configurations_component_instance_id",
        "port_configurations",
        ["component_instance_id"],
    )

    # Note: We don't create a global unique constraint on custom_port_name
    # because multiple component instances can have custom ports with the same name.
    # Uniqueness is enforced per component instance at the application level.

    # Create trigger function to validate that port configurations only reference INPUT ports
    # PostgreSQL doesn't support subqueries in CHECK constraints, so we use a trigger instead
    op.execute("""
        CREATE OR REPLACE FUNCTION validate_port_configuration_input_only()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Allow custom ports (null port_definition_id)
            IF NEW.port_definition_id IS NULL THEN
                RETURN NEW;
            END IF;

            -- Check if the port_definition is an INPUT port
            IF NOT EXISTS (
                SELECT 1 FROM port_definitions pd
                WHERE pd.id = NEW.port_definition_id
                AND pd.port_type = 'INPUT'
            ) THEN
                RAISE EXCEPTION 'Port configurations can only be created for INPUT ports, '
                    'not OUTPUT ports (port_definition_id: %)', NEW.port_definition_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger that fires before INSERT or UPDATE on port_configurations
    op.execute("""
        CREATE TRIGGER trg_validate_port_configuration_input_only
        BEFORE INSERT OR UPDATE OF port_definition_id
        ON port_configurations
        FOR EACH ROW
        EXECUTE FUNCTION validate_port_configuration_input_only();
    """)

    # Add nullable column with default True (ports are optional by default)
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

    # Update port_definitions.nullable from parameter definitions
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
            true  -- Default to nullable if no parameter definition found
        )
    """)

    # DATA MIGRATION: Convert existing tool_descriptions to port_configurations
    # Note: is_required_override can only make optional ports mandatory (is_required_override=True)
    # Cannot make required ports optional - they must always have a value for the component to work

    op.execute("""
        -- CTE to get effective tool_description_id (instance's or version's default)
        WITH effective_tool_descriptions AS (
            SELECT
                ci.id as component_instance_id,
                ci.component_version_id,
                COALESCE(ci.tool_description_id, cv.default_tool_description_id) as tool_description_id
            FROM component_instances ci
            INNER JOIN component_versions cv ON ci.component_version_id = cv.id
            WHERE COALESCE(ci.tool_description_id, cv.default_tool_description_id) IS NOT NULL
        )
        -- Insert base port_configurations for each component_instance with a tool_description
        INSERT INTO port_configurations (
            id,
            component_instance_id,
            port_definition_id,
            field_expression_id,
            config_type,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid() as id,
            etd.component_instance_id,
            pd.id as port_definition_id,
            NULL as field_expression_id,
            'tool_input' as config_type,
            NOW() as created_at,
            NOW() as updated_at
        FROM effective_tool_descriptions etd
        INNER JOIN tool_descriptions td ON etd.tool_description_id = td.id
        INNER JOIN port_definitions pd ON pd.component_version_id = etd.component_version_id
            AND pd.port_type = 'INPUT'
        -- Only create configs for ports that match tool_properties keys
        WHERE EXISTS (
            SELECT 1
            FROM jsonb_object_keys(td.tool_properties::jsonb) AS prop_key
            WHERE prop_key = pd.name
        );

        -- Insert child tool_input_configurations with overrides
        WITH effective_tool_descriptions AS (
            SELECT
                ci.id as component_instance_id,
                COALESCE(ci.tool_description_id, cv.default_tool_description_id) as tool_description_id
            FROM component_instances ci
            INNER JOIN component_versions cv ON ci.component_version_id = cv.id
            WHERE COALESCE(ci.tool_description_id, cv.default_tool_description_id) IS NOT NULL
        )
        INSERT INTO tool_input_configurations (
            id,
            setup_mode,
            ai_name_override,
            ai_description_override,
            is_required_override,
            custom_port_name,
            custom_port_description,
            custom_parameter_type,
            custom_ui_component_properties,
            json_schema_override
        )
        SELECT
            pc.id,
            'ai_filled' as setup_mode,
            -- No name override for standard ports
            NULL as ai_name_override,
            -- Extract description override from tool_properties
            CASE
                WHEN (td.tool_properties::jsonb->pd.name->>'description')::text IS NOT NULL
                     AND (td.tool_properties::jsonb->pd.name->>'description')::text != pd.description
                THEN (td.tool_properties::jsonb->pd.name->>'description')::text
                ELSE NULL
            END as ai_description_override,
            -- Set is_required_override based on required_tool_properties
            -- Only allow making optional ports mandatory, not making required ports optional
            CASE
                WHEN td.required_tool_properties::jsonb ? pd.name
                     AND pd.nullable = true
                THEN true  -- Port is optional but tool makes it required
                ELSE NULL  -- Use port definition default (cannot make required ports optional)
            END as is_required_override,
            NULL as custom_port_name,
            NULL as custom_port_description,
            NULL as custom_parameter_type,
            NULL as custom_ui_component_properties,
            -- Store full schema in json_schema_override if it's complex
            -- (has items, properties, enum, or other complex JSON Schema keywords)
            CASE
                WHEN td.tool_properties::jsonb->pd.name ? 'items'
                    OR td.tool_properties::jsonb->pd.name ? 'properties'
                    OR td.tool_properties::jsonb->pd.name ? 'enum'
                    OR td.tool_properties::jsonb->pd.name ? 'oneOf'
                    OR td.tool_properties::jsonb->pd.name ? 'anyOf'
                    OR td.tool_properties::jsonb->pd.name ? 'allOf'
                    OR (td.tool_properties::jsonb->pd.name->>'type')::text IN ('array', 'object')
                THEN td.tool_properties::jsonb->pd.name
                ELSE NULL
            END as json_schema_override
        FROM port_configurations pc
        INNER JOIN effective_tool_descriptions etd ON pc.component_instance_id = etd.component_instance_id
        INNER JOIN tool_descriptions td ON etd.tool_description_id = td.id
        INNER JOIN port_definitions pd ON pc.port_definition_id = pd.id
        WHERE pc.config_type = 'tool_input'
            AND pc.port_definition_id IS NOT NULL;

        -- Insert both port_configurations AND tool_input_configurations for CUSTOM PORTS
        -- We need to create them together with proper matching by using a materialized CTE
        WITH effective_tool_descriptions AS (
            SELECT
                ci.id as component_instance_id,
                ci.component_version_id,
                COALESCE(ci.tool_description_id, cv.default_tool_description_id) as tool_description_id
            FROM component_instances ci
            INNER JOIN component_versions cv ON ci.component_version_id = cv.id
            WHERE COALESCE(ci.tool_description_id, cv.default_tool_description_id) IS NOT NULL
        ),
        custom_port_data AS (
            -- Prepare all data for custom ports first
            SELECT
                gen_random_uuid() as new_id,
                etd.component_instance_id,
                td.required_tool_properties,
                td_prop.key as prop_name,
                td_prop.value as prop_value
            FROM effective_tool_descriptions etd
            INNER JOIN tool_descriptions td ON etd.tool_description_id = td.id
            CROSS JOIN LATERAL jsonb_each(td.tool_properties::jsonb) AS td_prop(key, value)
            WHERE NOT EXISTS (
                SELECT 1
                FROM port_definitions pd
                WHERE pd.component_version_id = etd.component_version_id
                  AND pd.port_type = 'INPUT'
                  AND pd.name = td_prop.key
            )
        ),
        inserted_port_configs AS (
            INSERT INTO port_configurations (
                id,
                component_instance_id,
                port_definition_id,
                field_expression_id,
                config_type,
                created_at,
                updated_at
            )
            SELECT
                new_id,
                component_instance_id,
                NULL as port_definition_id,
                NULL as field_expression_id,
                'tool_input' as config_type,
                NOW() as created_at,
                NOW() as updated_at
            FROM custom_port_data
            RETURNING id
        )
        INSERT INTO tool_input_configurations (
            id,
            setup_mode,
            ai_name_override,
            ai_description_override,
            is_required_override,
            custom_port_name,
            custom_port_description,
            custom_parameter_type,
            custom_ui_component_properties,
            json_schema_override
        )
        SELECT
            cpd.new_id,
            'ai_filled' as setup_mode,
            NULL as ai_name_override,
            NULL as ai_description_override,
            -- Custom ports are optional by default, only set override when explicitly required
            CASE
                WHEN cpd.required_tool_properties::jsonb ? cpd.prop_name
                THEN true
                ELSE NULL
            END as is_required_override,
            cpd.prop_name as custom_port_name,
            (cpd.prop_value->>'description')::text as custom_port_description,
            (CASE
                WHEN (cpd.prop_value->>'type')::text = 'string' THEN 'string'
                WHEN (cpd.prop_value->>'type')::text = 'integer' THEN 'integer'
                WHEN (cpd.prop_value->>'type')::text = 'number' THEN 'number'
                WHEN (cpd.prop_value->>'type')::text = 'boolean' THEN 'boolean'
                WHEN (cpd.prop_value->>'type')::text = 'object' THEN 'object'
                WHEN (cpd.prop_value->>'type')::text = 'array' THEN 'array'
                ELSE 'string'
            END)::json_schema_type as custom_parameter_type,
            cpd.prop_value as custom_ui_component_properties,
            -- Store full schema in json_schema_override if it's complex
            -- (has items, properties, enum, or other complex JSON Schema keywords)
            CASE
                WHEN cpd.prop_value ? 'items'
                    OR cpd.prop_value ? 'properties'
                    OR cpd.prop_value ? 'enum'
                    OR cpd.prop_value ? 'oneOf'
                    OR cpd.prop_value ? 'anyOf'
                    OR cpd.prop_value ? 'allOf'
                    OR (cpd.prop_value->>'type')::text IN ('array', 'object')
                THEN cpd.prop_value
                ELSE NULL
            END as json_schema_override
        FROM custom_port_data cpd;
    """)

    # Note: We don't delete tool_description_id or tool_descriptions table
    # to maintain backwards compatibility. The system will prefer port_configurations
    # if they exist (as per _get_tool_description logic)


def downgrade() -> None:
    # Drop child table first
    op.drop_table("tool_input_configurations")

    # Drop trigger and trigger function
    op.execute("DROP TRIGGER IF EXISTS trg_validate_port_configuration_input_only ON port_configurations;")
    op.execute("DROP FUNCTION IF EXISTS validate_port_configuration_input_only();")

    # Drop parent table
    op.drop_index("ix_port_configurations_component_instance_id", table_name="port_configurations")
    op.drop_table("port_configurations")

    drop_enum_if_exists(connection=op.get_bind(), enum_name="port_setup_mode")
    drop_enum_if_exists(connection=op.get_bind(), enum_name="json_schema_type")

    op.drop_column("port_definitions", "nullable")
