"""Migrate Start payload_schema from BasicParameter to FieldExpression + InputPortInstance.

Creates an INPUT PortDefinition for payload_schema (drives_output_schema=True) and migrates
all existing BasicParameter rows to FieldExpression LiteralNodes + InputPortInstances,
matching the same pattern used in b2c3d4e5f6a7.

Revision ID: c4d5e6f7a8b9
Revises: a3b4c5d6e7f8
Create Date: 2026-03-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

START_V2_COMPONENT_VERSION_ID = "7a6e2c9b-5b1b-4a9b-9f2f-9b7f0540d4b0"

# ComponentParameterDefinition for payload_schema (from seed_start.py before migration).
PAYLOAD_SCHEMA_CPD_ID = "1e50db7d-87cb-4c90-9082-451c4cbf93f9"

# Fixed UUID for the new PortDefinition — referenced by both upgrade and downgrade.
PAYLOAD_SCHEMA_PORT_DEF_ID = "e5f6a7b8-c9d0-4321-abcd-ef0123456789"

PAYLOAD_SCHEMA_DEFAULT = '{"messages": [{"role": "user", "content": "Hello"}]}'

PAYLOAD_SCHEMA_UI_PROPS = (
    '{"label": "Payload Schema", "description": "Defines the structure of input data for this workflow. '
    "Keys can be referenced as template variables (e.g., @{{additional_info}}). "
    'Values serve as defaults when not provided in requests."}'
)


def upgrade() -> None:
    bind = op.get_bind()

    # --- Pre-migration snapshot ---
    # UUIDs are embedded directly in f-strings (safe — hardcoded constants) to avoid the
    # SQLAlchemy :param::cast syntax conflict where `::uuid` looks like a second colon-param.
    rows_before = bind.execute(
        sa.text(f"""
            SELECT COUNT(*) FROM basic_parameters
            WHERE parameter_definition_id = '{PAYLOAD_SCHEMA_CPD_ID}'::uuid
        """),
    ).scalar()

    # 2a. Create the INPUT PortDefinition for payload_schema.
    # Alembic runs before seed, so seed_ports.py hasn't created this yet.
    # WHERE EXISTS makes this a no-op on empty DBs (e.g. alembic tests) where the component_version doesn't exist yet.
    bind.execute(
        sa.text(f"""
            INSERT INTO port_definitions (
                id, component_version_id, name, port_type, is_canonical,
                description, parameter_type, ui_component, ui_component_properties,
                nullable, "default", is_tool_input, is_advanced, drives_output_schema
            )
            SELECT
                '{PAYLOAD_SCHEMA_PORT_DEF_ID}'::uuid,
                '{START_V2_COMPONENT_VERSION_ID}'::uuid,
                'payload_schema',
                'INPUT'::port_type,
                false,
                'Defines the structure of input data for this workflow.',
                'json'::parameter_type,
                'JSON Builder'::ui_component,
                CAST(:ui_props AS jsonb),
                false,
                :default_val,
                false,
                false,
                true
            WHERE EXISTS (
                SELECT 1 FROM component_versions WHERE id = '{START_V2_COMPONENT_VERSION_ID}'::uuid
            )
            ON CONFLICT ON CONSTRAINT unique_component_version_port DO NOTHING
        """),
        {
            "ui_props": PAYLOAD_SCHEMA_UI_PROPS,
            "default_val": PAYLOAD_SCHEMA_DEFAULT,
        },
    )

    # 2b. Migrate basic_parameters → field_expressions + port_instances + input_port_instances.
    # Pattern identical to b2c3d4e5f6a7. DISTINCT ON guards against duplicate basic_parameter rows.
    # The value is stored as a string literal (LiteralNode.value: str), consistent with the
    # field expression serializer which always wraps values as strings.
    bind.execute(
        sa.text(f"""
            WITH source AS (
                SELECT DISTINCT ON (bp.component_instance_id)
                    bp.component_instance_id,
                    COALESCE(bp.value, :default_val)  AS value,
                    gen_random_uuid()                  AS new_fe_id,
                    gen_random_uuid()                  AS new_pi_id
                FROM basic_parameters bp
                WHERE bp.parameter_definition_id = '{PAYLOAD_SCHEMA_CPD_ID}'::uuid
                ORDER BY bp.component_instance_id, bp.id
            ),
            insert_fe AS (
                INSERT INTO field_expressions (id, expression_json, updated_at)
                SELECT
                    new_fe_id,
                    jsonb_build_object('type', 'literal', 'value', value),
                    now()
                FROM source
                RETURNING id
            ),
            upsert_pi AS (
                INSERT INTO port_instances (id, component_instance_id, name, port_definition_id, type, created_at)
                SELECT
                    new_pi_id,
                    component_instance_id,
                    'payload_schema',
                    '{PAYLOAD_SCHEMA_PORT_DEF_ID}'::uuid,
                    'INPUT'::port_type,
                    now()
                FROM source
                ON CONFLICT ON CONSTRAINT uq_port_instance_name
                DO UPDATE SET port_definition_id = '{PAYLOAD_SCHEMA_PORT_DEF_ID}'::uuid
                RETURNING id, component_instance_id
            ),
            upsert_ipi AS (
                INSERT INTO input_port_instances (id, field_expression_id)
                SELECT
                    upsert_pi.id,
                    insert_fe.id
                FROM upsert_pi
                JOIN source ON upsert_pi.component_instance_id = source.component_instance_id
                JOIN insert_fe ON insert_fe.id = source.new_fe_id
                ON CONFLICT (id)
                DO UPDATE SET field_expression_id = EXCLUDED.field_expression_id
            )
            DELETE FROM basic_parameters
            WHERE parameter_definition_id = '{PAYLOAD_SCHEMA_CPD_ID}'::uuid
        """),
        {"default_val": PAYLOAD_SCHEMA_DEFAULT},
    )

    # 2c. Drop the now-stale ComponentParameterDefinition.
    bind.execute(
        sa.text(f"""
            DELETE FROM component_parameter_definitions
            WHERE id = '{PAYLOAD_SCHEMA_CPD_ID}'::uuid
        """),
    )

    # --- Post-migration assertions ---
    component_version_exists = bind.execute(
        sa.text(f"SELECT 1 FROM component_versions WHERE id = '{START_V2_COMPONENT_VERSION_ID}'::uuid"),
    ).fetchone() is not None
    _assert_upgrade_succeeded(bind, rows_before, component_version_exists)


def _assert_upgrade_succeeded(bind, rows_before: int, component_version_exists: bool) -> None:
    """Raise if the upgrade left the DB in an inconsistent state."""

    # No basic_parameters rows should remain for payload_schema.
    remaining_bp = bind.execute(
        sa.text(f"""
            SELECT COUNT(*) FROM basic_parameters
            WHERE parameter_definition_id = '{PAYLOAD_SCHEMA_CPD_ID}'::uuid
        """),
    ).scalar()
    if remaining_bp != 0:
        raise RuntimeError(
            f"[c4d5e6f7a8b9] upgrade: {remaining_bp} basic_parameters rows still exist for payload_schema CPD — "
            "expected 0 after migration."
        )

    # The PortDefinition must exist and have drives_output_schema=True.
    # Skipped when component_version doesn't exist (empty DB) — the INSERT was intentionally a no-op.
    if component_version_exists:
        pd_row = bind.execute(
            sa.text(f"""
                SELECT drives_output_schema FROM port_definitions
                WHERE id = '{PAYLOAD_SCHEMA_PORT_DEF_ID}'::uuid
            """),
        ).fetchone()
        if pd_row is None:
            raise RuntimeError(
                f"[c4d5e6f7a8b9] upgrade: PortDefinition {PAYLOAD_SCHEMA_PORT_DEF_ID} not found after INSERT."
            )
        if not pd_row[0]:
            raise RuntimeError(
                f"[c4d5e6f7a8b9] upgrade: PortDefinition {PAYLOAD_SCHEMA_PORT_DEF_ID} has "
                "drives_output_schema=False — expected True."
            )

    # The count of migrated input_port_instances must equal the original basic_parameters count.
    migrated_count = bind.execute(
        sa.text(f"""
            SELECT COUNT(*)
            FROM input_port_instances ipi
            JOIN port_instances pi ON pi.id = ipi.id
            WHERE pi.name = 'payload_schema'
              AND pi.port_definition_id = '{PAYLOAD_SCHEMA_PORT_DEF_ID}'::uuid
        """),
    ).scalar()
    # Only enforce the equality when there was something to migrate.
    # If rows_before == 0 the migration was already applied (or the DB is empty) — both are fine.
    if rows_before > 0 and migrated_count != rows_before:
        raise RuntimeError(
            f"[c4d5e6f7a8b9] upgrade: expected {rows_before} input_port_instances for payload_schema, "
            f"got {migrated_count}."
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Re-create the ComponentParameterDefinition so the restore step can reference it.
    # WHERE EXISTS makes this a no-op on empty DBs where the component_version doesn't exist.
    bind.execute(
        sa.text(f"""
            INSERT INTO component_parameter_definitions
                (id, component_version_id, name, type, nullable, is_advanced)
            SELECT
                '{PAYLOAD_SCHEMA_CPD_ID}'::uuid,
                '{START_V2_COMPONENT_VERSION_ID}'::uuid,
                'payload_schema',
                'json'::parameter_type,
                false,
                false
            WHERE EXISTS (
                SELECT 1 FROM component_versions WHERE id = '{START_V2_COMPONENT_VERSION_ID}'::uuid
            )
            ON CONFLICT (id) DO NOTHING
        """),
    )

    # Restore BasicParameter rows from InputPortInstance + FieldExpression (literal values only).
    # Then delete the port_instances rows (cascades to input_port_instances).
    bind.execute(
        sa.text(f"""
            WITH source AS (
                SELECT
                    ipi.id                          AS ipi_id,
                    pi.component_instance_id,
                    fe.expression_json->>'value'    AS literal_value
                FROM input_port_instances ipi
                JOIN port_instances pi ON pi.id = ipi.id
                JOIN field_expressions fe ON ipi.field_expression_id = fe.id
                WHERE pi.name = 'payload_schema'
                  AND pi.port_definition_id = '{PAYLOAD_SCHEMA_PORT_DEF_ID}'::uuid
                  AND fe.expression_json->>'type' = 'literal'
            ),
            restore_bp AS (
                INSERT INTO basic_parameters (id, component_instance_id, parameter_definition_id, value)
                SELECT gen_random_uuid(), component_instance_id, '{PAYLOAD_SCHEMA_CPD_ID}'::uuid, literal_value
                FROM source
                ON CONFLICT DO NOTHING
            )
            DELETE FROM port_instances
            WHERE id IN (SELECT ipi_id FROM source)
        """),
    )

    # Remove the PortDefinition created in upgrade.
    bind.execute(
        sa.text(f"""
            DELETE FROM port_definitions
            WHERE id = '{PAYLOAD_SCHEMA_PORT_DEF_ID}'::uuid
        """),
    )
