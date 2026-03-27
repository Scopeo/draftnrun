"""add tool port configurations

Revision ID: a3b7c9d1e5f2
Revises: d3e4f5a6b7c8
Create Date: 2026-03-18 10:00:00.000000

"""

import json
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ada_backend.database.utils import create_enum_if_not_exists, drop_enum_if_exists

LOGGER = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "a3b7c9d1e5f2"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRIGGER_FN_CHECK_IS_TOOL_INPUT = """\
CREATE OR REPLACE FUNCTION trg_tool_port_config_check_is_tool_input()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.port_definition_id IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM port_definitions
            WHERE id = NEW.port_definition_id
              AND is_tool_input = TRUE
        ) THEN
            RAISE EXCEPTION
                'ToolPortConfiguration.port_definition_id (%) references a '
                'PortDefinition with is_tool_input=FALSE',
                NEW.port_definition_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER_CHECK_IS_TOOL_INPUT = """\
CREATE TRIGGER tool_port_config_check_is_tool_input
BEFORE INSERT OR UPDATE OF port_definition_id
ON tool_port_configurations
FOR EACH ROW
EXECUTE FUNCTION trg_tool_port_config_check_is_tool_input();
"""

TRIGGER_FN_PREVENT_UNSET = """\
CREATE OR REPLACE FUNCTION trg_port_def_prevent_unset_is_tool_input()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.is_tool_input = TRUE AND NEW.is_tool_input = FALSE THEN
        IF EXISTS (
            SELECT 1 FROM tool_port_configurations
            WHERE port_definition_id = NEW.id
        ) THEN
            RAISE EXCEPTION
                'Cannot set is_tool_input=FALSE on PortDefinition (%) '
                'while ToolPortConfiguration rows reference it',
                NEW.id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER_PREVENT_UNSET = """\
CREATE TRIGGER port_def_prevent_unset_is_tool_input
BEFORE UPDATE OF is_tool_input
ON port_definitions
FOR EACH ROW
EXECUTE FUNCTION trg_port_def_prevent_unset_is_tool_input();
"""

SIMPLE_TYPE_MAPPING = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "json": "object",
    "object": "object",
    "array": "array",
}


def _is_complex_schema(prop_value: dict) -> bool:
    """Return True if a property schema has fields beyond simple type + description."""
    extra_keys = set(prop_value.keys()) - {"type", "description"}
    return bool(extra_keys)


def upgrade() -> None:
    connection = op.get_bind()

    create_enum_if_not_exists(connection, ["ai_filled", "user_set", "deactivated"], "port_setup_mode")
    create_enum_if_not_exists(
        connection, ["string", "integer", "number", "boolean", "object", "array"], "json_schema_type"
    )

    port_setup_mode_enum = postgresql.ENUM(
        "ai_filled", "user_set", "deactivated", name="port_setup_mode", create_type=False
    )
    json_schema_type_enum = postgresql.ENUM(
        "string", "integer", "number", "boolean", "object", "array", name="json_schema_type", create_type=False
    )

    op.create_table(
        "tool_port_configurations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("component_instance_id", sa.UUID(), nullable=False),
        sa.Column("input_port_instance_id", sa.UUID(), nullable=True),
        sa.Column("port_definition_id", sa.UUID(), nullable=True),
        sa.Column(
            "setup_mode",
            port_setup_mode_enum,
            nullable=False,
            server_default="ai_filled",
        ),
        sa.Column("ai_name_override", sa.String(), nullable=True),
        sa.Column("ai_description_override", sa.Text(), nullable=True),
        sa.Column(
            "is_required_override",
            sa.Boolean(),
            nullable=True,
            comment="Override required status: True=mandatory, False=optional, None=use port definition default",
        ),
        sa.Column("custom_parameter_type", json_schema_type_enum, nullable=True),
        sa.Column(
            "json_schema_override",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Full JSON Schema for complex parameter types. Overrides simple type mapping.",
        ),
        sa.Column("expression_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("custom_ui_component_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["component_instance_id"],
            ["component_instances.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["input_port_instance_id"],
            ["input_port_instances.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["port_definition_id"],
            ["port_definitions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "component_instance_id",
            "port_definition_id",
            name="uq_tool_port_config_instance_port_def",
        ),
    )
    op.create_index(
        op.f("ix_tool_port_configurations_component_instance_id"),
        "tool_port_configurations",
        ["component_instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_port_configurations_input_port_instance_id"),
        "tool_port_configurations",
        ["input_port_instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_port_configurations_port_definition_id"),
        "tool_port_configurations",
        ["port_definition_id"],
        unique=False,
    )
    op.create_index(
        "uq_tool_port_config_instance_ai_name",
        "tool_port_configurations",
        ["component_instance_id", "ai_name_override"],
        unique=True,
        postgresql_where=sa.text("port_definition_id IS NULL AND ai_name_override IS NOT NULL"),
    )

    # ---- Data migration ----
    # Pass 1: ports with is_tool_input=True that already have PortDefinitions.
    # Only creates a ToolPortConfiguration when the port name is explicitly listed
    # in the resolved tool_properties of the associated ToolDescription. Ports that
    # exist in the code with is_tool_input=True but are absent from tool_properties
    # (e.g. the RAG/Retriever `filters` port) are intentionally excluded.
    rows = connection.execute(
        sa.text("""
            SELECT
                ci.id AS component_instance_id,
                pd.id AS port_definition_id,
                pd.name AS port_name,
                pd.description AS port_description,
                COALESCE(td_instance.tool_properties::jsonb, td_version.tool_properties::jsonb) AS tool_properties
            FROM component_instances ci
            JOIN component_versions cv ON ci.component_version_id = cv.id
            JOIN port_definitions pd ON pd.component_version_id = cv.id
                AND pd.port_type = 'INPUT'
                AND pd.is_tool_input = TRUE
            LEFT JOIN tool_descriptions td_instance ON ci.tool_description_id = td_instance.id
            LEFT JOIN tool_descriptions td_version ON cv.default_tool_description_id = td_version.id
            WHERE COALESCE(td_instance.tool_properties::jsonb, td_version.tool_properties::jsonb) ? pd.name
        """)
    )

    port_def_config_count = 0
    for row in rows:
        component_instance_id = row[0]
        port_definition_id = row[1]
        port_name = row[2]
        port_description = row[3]
        tool_properties = row[4]

        ai_description_override = None
        if tool_properties and isinstance(tool_properties, dict):
            prop = tool_properties.get(port_name)
            if prop and isinstance(prop, dict):
                static_desc = prop.get("description")
                if static_desc and static_desc != port_description:
                    ai_description_override = static_desc

        connection.execute(
            sa.text("""
                INSERT INTO tool_port_configurations
                    (id, component_instance_id, port_definition_id, setup_mode, ai_description_override)
                VALUES
                    (gen_random_uuid(), :ci_id, :pd_id, 'ai_filled', :ai_desc)
                ON CONFLICT (component_instance_id, port_definition_id) DO NOTHING
            """),
            {
                "ci_id": component_instance_id,
                "pd_id": port_definition_id,
                "ai_desc": ai_description_override,
            },
        )
        port_def_config_count += 1
    LOGGER.info(f"Pass 1: created {port_def_config_count} port-def-backed configs")

    # Pass 1b: ports with is_tool_input=True that belong to a component with a tool
    # description but are NOT listed in that tool description's tool_properties.
    # These ports are explicitly deactivated so the service does not fall back to
    # AI_FILLED for them (e.g. the RAG/Retriever `filters` port).
    deactivated_rows = connection.execute(
        sa.text("""
            SELECT
                ci.id AS component_instance_id,
                pd.id AS port_definition_id
            FROM component_instances ci
            JOIN component_versions cv ON ci.component_version_id = cv.id
            JOIN port_definitions pd ON pd.component_version_id = cv.id
                AND pd.port_type = 'INPUT'
                AND pd.is_tool_input = TRUE
            LEFT JOIN tool_descriptions td_instance ON ci.tool_description_id = td_instance.id
            LEFT JOIN tool_descriptions td_version ON cv.default_tool_description_id = td_version.id
            WHERE (ci.tool_description_id IS NOT NULL OR cv.default_tool_description_id IS NOT NULL)
              AND NOT (COALESCE(td_instance.tool_properties::jsonb, td_version.tool_properties::jsonb) ? pd.name)
        """)
    )

    deactivated_count = 0
    for row in deactivated_rows:
        connection.execute(
            sa.text("""
                INSERT INTO tool_port_configurations
                    (id, component_instance_id, port_definition_id, setup_mode)
                VALUES
                    (gen_random_uuid(), :ci_id, :pd_id, 'deactivated')
                ON CONFLICT (component_instance_id, port_definition_id) DO NOTHING
            """),
            {
                "ci_id": row[0],
                "pd_id": row[1],
            },
        )
        deactivated_count += 1
    LOGGER.info(f"Pass 1b: created {deactivated_count} deactivated configs for ports absent from tool_properties")

    # Pass 2: custom tool_properties that have NO matching PortDefinition.
    # These are AI-filled parameters defined only in the ToolDescription
    # (common for API Call, where users add custom query params).
    custom_rows = connection.execute(
        sa.text("""
            SELECT
                ci.id AS component_instance_id,
                ci.name AS instance_name,
                cv.id AS component_version_id,
                COALESCE(td_instance.tool_properties::jsonb, td_version.tool_properties::jsonb) AS tool_properties,
                COALESCE(
                    td_instance.required_tool_properties::jsonb,
                    td_version.required_tool_properties::jsonb
                ) AS required_tool_properties
            FROM component_instances ci
            JOIN component_versions cv ON ci.component_version_id = cv.id
            LEFT JOIN tool_descriptions td_instance ON ci.tool_description_id = td_instance.id
            LEFT JOIN tool_descriptions td_version ON cv.default_tool_description_id = td_version.id
            WHERE ci.tool_description_id IS NOT NULL
               OR cv.default_tool_description_id IS NOT NULL
        """)
    )

    custom_config_count = 0
    for row in custom_rows:
        component_instance_id = row[0]
        instance_name = row[1]
        component_version_id = row[2]
        tool_properties = row[3]
        required_tool_properties = row[4]

        if not tool_properties or not isinstance(tool_properties, dict):
            continue

        port_def_result = connection.execute(
            sa.text("""
                SELECT name FROM port_definitions
                WHERE component_version_id = :cv_id
                  AND port_type = 'INPUT'
                  AND is_tool_input = TRUE
            """),
            {"cv_id": component_version_id},
        )
        tool_port_def_names = {r[0] for r in port_def_result}

        required_set = (
            set(required_tool_properties)
            if required_tool_properties and isinstance(required_tool_properties, list)
            else set()
        )

        for prop_name, prop_value in tool_properties.items():
            if prop_name in tool_port_def_names:
                continue

            if not isinstance(prop_value, dict):
                continue

            raw_type = prop_value.get("type", "string")
            is_complex = _is_complex_schema(prop_value) or not isinstance(raw_type, str)
            custom_type = SIMPLE_TYPE_MAPPING.get(raw_type, "string") if isinstance(raw_type, str) else "string"
            prop_description = prop_value.get("description")
            is_required = prop_name in required_set

            json_schema_override = None
            if is_complex:
                json_schema_override = json.dumps(prop_value)

            connection.execute(
                sa.text("""
                    INSERT INTO tool_port_configurations
                        (id, component_instance_id, port_definition_id, setup_mode,
                         ai_name_override, ai_description_override,
                         custom_parameter_type, is_required_override,
                         json_schema_override)
                    SELECT
                        gen_random_uuid(), :ci_id, NULL, 'ai_filled',
                        :name, :desc,
                        CAST(:param_type AS json_schema_type), :is_required,
                        :json_schema
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM tool_port_configurations tpc
                        WHERE tpc.component_instance_id = :ci_id
                          AND tpc.port_definition_id IS NULL
                          AND tpc.ai_name_override = :name
                    )
                """),
                {
                    "ci_id": component_instance_id,
                    "name": prop_name,
                    "desc": prop_description,
                    "param_type": custom_type,
                    "is_required": is_required,
                    "json_schema": json_schema_override,
                },
            )
            custom_config_count += 1
            LOGGER.info(f"  Custom port '{prop_name}' for instance '{instance_name}' ({component_instance_id})")

    LOGGER.info(f"Pass 2: created {custom_config_count} custom (non-port-def) configs")

    # ---- Add tool_description_override column ----
    op.add_column("component_instances", sa.Column("tool_description_override", sa.Text(), nullable=True))

    connection.execute(
        sa.text("""
            UPDATE component_instances ci
            SET tool_description_override = td.description
            FROM tool_descriptions td
            WHERE ci.tool_description_id = td.id
              AND ci.tool_description_id IS NOT NULL
        """)
    )

    # Keep tool_description_id and default_tool_description_id as deprecated
    # columns so downgrade doesn't lose data.  Drop the FK constraints only
    # (the application code no longer uses these columns).
    op.drop_constraint(
        "component_instances_tool_description_id_fkey",
        "component_instances",
        type_="foreignkey",
    )
    op.drop_constraint(
        "component_versions_default_tool_description_id_fkey",
        "component_versions",
        type_="foreignkey",
    )

    # ---- DB-level enforcement: only is_tool_input=True ports allowed ----
    connection.execute(sa.text(TRIGGER_FN_CHECK_IS_TOOL_INPUT))
    connection.execute(sa.text(TRIGGER_CHECK_IS_TOOL_INPUT))
    connection.execute(sa.text(TRIGGER_FN_PREVENT_UNSET))
    connection.execute(sa.text(TRIGGER_PREVENT_UNSET))


def downgrade() -> None:
    # Drop triggers before dropping the table they reference
    op.execute("DROP TRIGGER IF EXISTS tool_port_config_check_is_tool_input ON tool_port_configurations")
    op.execute("DROP FUNCTION IF EXISTS trg_tool_port_config_check_is_tool_input()")
    op.execute("DROP TRIGGER IF EXISTS port_def_prevent_unset_is_tool_input ON port_definitions")
    op.execute("DROP FUNCTION IF EXISTS trg_port_def_prevent_unset_is_tool_input()")
    # Restore FK constraints on the deprecated columns (they were NOT dropped).
    op.create_foreign_key(
        "component_versions_default_tool_description_id_fkey",
        "component_versions",
        "tool_descriptions",
        ["default_tool_description_id"],
        ["id"],
    )
    op.create_foreign_key(
        "component_instances_tool_description_id_fkey",
        "component_instances",
        "tool_descriptions",
        ["tool_description_id"],
        ["id"],
    )

    op.drop_column("component_instances", "tool_description_override")

    op.drop_index(
        "uq_tool_port_config_instance_ai_name",
        table_name="tool_port_configurations",
    )
    op.drop_index(
        op.f("ix_tool_port_configurations_port_definition_id"),
        table_name="tool_port_configurations",
    )
    op.drop_index(
        op.f("ix_tool_port_configurations_input_port_instance_id"),
        table_name="tool_port_configurations",
    )
    op.drop_index(
        op.f("ix_tool_port_configurations_component_instance_id"),
        table_name="tool_port_configurations",
    )
    op.drop_table("tool_port_configurations")

    connection = op.get_bind()
    drop_enum_if_exists(connection, "json_schema_type")
    drop_enum_if_exists(connection, "port_setup_mode")
