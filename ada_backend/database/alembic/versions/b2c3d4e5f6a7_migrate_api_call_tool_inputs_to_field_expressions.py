"""migrate api_call_tool endpoint, headers and fixed_parameters
from BasicParameter to FieldExpression.

Revision ID: b2c3d4e5f6a7
Revises: d0e1f2a3b4c5
Create Date: 2026-02-25 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Known ComponentParameterDefinition IDs (from seed_api_call_tool.py before migration).
ENDPOINT_PARAM_DEF_ID = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
HEADERS_PARAM_DEF_ID = "d4e5f6a7-b8c9-0123-def1-234567890123"
FIXED_PARAMETERS_PARAM_DEF_ID = "a7b8c9d0-e1f2-3456-1234-567890123456"

STALE_CPD_IDS = [
    ENDPOINT_PARAM_DEF_ID,
    HEADERS_PARAM_DEF_ID,
    FIXED_PARAMETERS_PARAM_DEF_ID,
]
_STALE_CPD_IDS_ARRAY = "ARRAY[" + ", ".join(f"'{i}'::uuid" for i in STALE_CPD_IDS) + "]"


def upgrade() -> None:
    bind = op.get_bind()

    # Migrate only API Call tool params (by CPD id).
    # input_port_instances is now a child table of port_instances (joined-table inheritance
    # introduced in d0e1f2a3b4c5): columns component_instance_id/name/port_definition_id/
    # created_at live in port_instances; input_port_instances only holds id + field_expression_id.
    #
    # DISTINCT ON ensures one row per (component_instance_id, param_name) even when duplicate
    # BasicParameter rows exist; the final DELETE removes ALL matching rows so no orphans remain.
    bind.execute(
        sa.text(f"""
        WITH source AS (
            SELECT DISTINCT ON (bp.component_instance_id, cpd.name)
                bp.component_instance_id,
                COALESCE(bp.value, '')  AS value,
                cpd.name                AS param_name,
                gen_random_uuid()       AS new_fe_id,
                gen_random_uuid()       AS new_pi_id
            FROM basic_parameters bp
            JOIN component_parameter_definitions cpd
              ON bp.parameter_definition_id = cpd.id
            WHERE cpd.id = ANY({_STALE_CPD_IDS_ARRAY})
            ORDER BY bp.component_instance_id, cpd.name, bp.id
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
                param_name,
                NULL,
                'INPUT'::port_type,
                now()
            FROM source
            ON CONFLICT ON CONSTRAINT uq_port_instance_name
            DO UPDATE SET port_definition_id = NULL
            RETURNING id, name, component_instance_id
        ),
        upsert_ipi AS (
            INSERT INTO input_port_instances (id, field_expression_id)
            SELECT
                upsert_pi.id,
                insert_fe.id
            FROM upsert_pi
            JOIN source ON upsert_pi.component_instance_id = source.component_instance_id
                       AND upsert_pi.name = source.param_name
            JOIN insert_fe ON insert_fe.id = source.new_fe_id
            ON CONFLICT (id)
            DO UPDATE SET field_expression_id = EXCLUDED.field_expression_id
        )
        DELETE FROM basic_parameters bp
        USING component_parameter_definitions cpd
        WHERE bp.parameter_definition_id = cpd.id
          AND cpd.id = ANY({_STALE_CPD_IDS_ARRAY})
    """)
    )

    # Delete the stale ComponentParameterDefinition rows. These parameters are
    # now handled as port definitions (seeded via seed_ports.py from the
    # component's input schema), so the CPD rows are obsolete.
    bind.execute(
        sa.text(f"""
        DELETE FROM component_parameter_definitions
        WHERE id = ANY({_STALE_CPD_IDS_ARRAY})
    """)
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Re-create the CPD rows that were deleted in upgrade so the JOIN in the
    # data-restore step below can find them.
    bind.execute(
        sa.text(f"""
        INSERT INTO component_parameter_definitions
            (id, component_version_id, name, type, nullable, is_advanced)
        SELECT
            cpd_data.id::uuid,
            cv.id,
            cpd_data.param_name,
            'string'::parameter_type,
            cpd_data.is_nullable,
            FALSE
        FROM (VALUES
            ('{ENDPOINT_PARAM_DEF_ID}',         'API Call', 'endpoint',         FALSE::boolean),
            ('{HEADERS_PARAM_DEF_ID}',          'API Call', 'headers',          TRUE::boolean),
            ('{FIXED_PARAMETERS_PARAM_DEF_ID}', 'API Call', 'fixed_parameters', TRUE::boolean)
        ) AS cpd_data(id, component_name, param_name, is_nullable)
        CROSS JOIN LATERAL (
            SELECT cv2.id
            FROM component_versions cv2
            JOIN components c ON c.id = cv2.component_id
            WHERE c.name = cpd_data.component_name
            LIMIT 1
        ) AS cv(id)
        ON CONFLICT (id) DO NOTHING
    """)
    )

    # Restore BasicParameter rows from InputPortInstance + FieldExpression.
    # Only literal expressions can be converted back; injected (ref/concat) values are left as-is.
    # After d0e1f2a3b4c5, input_port_instances is a child of port_instances: name/
    # component_instance_id/port_definition_id now live in port_instances, so we JOIN to get them.
    # Deleting from port_instances cascades to input_port_instances.
    bind.execute(
        sa.text("""
        WITH source AS (
            SELECT
                ipi.id                          AS ipi_id,
                pi.component_instance_id,
                pi.name                         AS param_name,
                fe.expression_json->>'value'    AS literal_value,
                cpd.id                          AS param_def_id
            FROM input_port_instances ipi
            JOIN port_instances pi ON pi.id = ipi.id
            JOIN field_expressions fe
              ON ipi.field_expression_id = fe.id
            JOIN component_parameter_definitions cpd
              ON cpd.name = pi.name
             AND cpd.id = ANY(ARRAY[
                    :endpoint_def_id         ::uuid,
                    :headers_def_id          ::uuid,
                    :fixed_parameters_def_id ::uuid
                 ])
            WHERE pi.name = ANY(ARRAY['endpoint', 'headers', 'fixed_parameters'])
              AND pi.port_definition_id IS NULL
              AND fe.expression_json->>'type' = 'literal'
        ),
        restore_bp AS (
            INSERT INTO basic_parameters (id, component_instance_id, parameter_definition_id, value)
            SELECT gen_random_uuid(), component_instance_id, param_def_id, literal_value
            FROM source
            ON CONFLICT DO NOTHING
        )
        DELETE FROM port_instances
        WHERE id IN (SELECT ipi_id FROM source)
    """),
        {
            "endpoint_def_id": ENDPOINT_PARAM_DEF_ID,
            "headers_def_id": HEADERS_PARAM_DEF_ID,
            "fixed_parameters_def_id": FIXED_PARAMETERS_PARAM_DEF_ID,
        },
    )
