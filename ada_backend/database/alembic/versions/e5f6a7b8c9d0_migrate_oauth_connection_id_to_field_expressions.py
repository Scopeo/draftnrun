"""migrate oauth_connection_id from BasicParameter to FieldExpression
for Gmail v2, Slack, HubSpot MCP, and HubSpot Neverdrop MCP.

Revision ID: e5f6a7b8c9d0
Revises: dwh7zeh4dibz
Create Date: 2026-03-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "dwh7zeh4dibz"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ComponentParameterDefinition IDs for oauth_connection_id (from seed files before migration).
GMAIL_V2_OAUTH_CPD_ID = "c205b8b5-61aa-485b-af33-c9e7e67792db"
SLACK_OAUTH_CPD_ID = "7263b707-51ca-4d64-abfd-6c0907b3e860"
HUBSPOT_MCP_OAUTH_CPD_ID = "8a7b6c5d-4e3f-2a1b-0c9d-8e7f6a5b4c3d"
HUBSPOT_NEVERDROP_MCP_OAUTH_CPD_ID = "50ded9b8-5d59-486b-8c5e-91eeed909dc1"

STALE_CPD_IDS = [
    GMAIL_V2_OAUTH_CPD_ID,
    SLACK_OAUTH_CPD_ID,
    HUBSPOT_MCP_OAUTH_CPD_ID,
    HUBSPOT_NEVERDROP_MCP_OAUTH_CPD_ID,
]
_STALE_CPD_IDS_ARRAY = "ARRAY[" + ", ".join(f"'{i}'::uuid" for i in STALE_CPD_IDS) + "]"

# Mapping of CPD ID -> (component_name, version_tag) for downgrade re-creation.
_CPD_COMPONENT_MAP = {
    GMAIL_V2_OAUTH_CPD_ID: "Gmail Sender",
    SLACK_OAUTH_CPD_ID: "Slack Sender",
    HUBSPOT_MCP_OAUTH_CPD_ID: "HubSpot MCP Tool",
    HUBSPOT_NEVERDROP_MCP_OAUTH_CPD_ID: "HubSpot Neverdrop MCP Tool",
}


def upgrade() -> None:
    bind = op.get_bind()

    # Migrate oauth_connection_id BasicParameter rows to InputPortInstance + FieldExpression.
    # The old BasicParameter value is an OrgVariableDefinition UUID.  We look up the
    # definition name and store a VarNode ({"type": "var", "name": "<name>"}) so the
    # GraphRunner resolves the variable at runtime (including variable-set overrides).
    bind.execute(
        sa.text(f"""
        WITH source AS (
            SELECT DISTINCT ON (bp.component_instance_id, cpd.name)
                bp.component_instance_id,
                ovd.name                AS var_name,
                cpd.name                AS param_name,
                gen_random_uuid()       AS new_fe_id,
                gen_random_uuid()       AS new_pi_id
            FROM basic_parameters bp
            JOIN component_parameter_definitions cpd
              ON bp.parameter_definition_id = cpd.id
            JOIN org_variable_definitions ovd
              ON ovd.id = bp.value::uuid
            WHERE cpd.id = ANY({_STALE_CPD_IDS_ARRAY})
              AND bp.value IS NOT NULL
              AND bp.value != ''
            ORDER BY bp.component_instance_id, cpd.name, bp.id
        ),
        insert_fe AS (
            INSERT INTO field_expressions (id, expression_json, updated_at)
            SELECT
                new_fe_id,
                jsonb_build_object('type', 'var', 'name', var_name),
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

    bind.execute(
        sa.text(f"""
        DELETE FROM component_parameter_definitions
        WHERE id = ANY({_STALE_CPD_IDS_ARRAY})
    """)
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Re-create the CPD rows that were deleted in upgrade.
    # All four are oauth_connection_id with type=string, nullable=false.
    bind.execute(
        sa.text(f"""
        INSERT INTO component_parameter_definitions
            (id, component_version_id, name, type, nullable, is_advanced)
        SELECT
            cpd_data.id::uuid,
            cv.id,
            'oauth_connection_id',
            'string'::parameter_type,
            FALSE,
            FALSE
        FROM (VALUES
            ('{GMAIL_V2_OAUTH_CPD_ID}',              'Gmail Sender'),
            ('{SLACK_OAUTH_CPD_ID}',                  'Slack Sender'),
            ('{HUBSPOT_MCP_OAUTH_CPD_ID}',            'HubSpot MCP Tool'),
            ('{HUBSPOT_NEVERDROP_MCP_OAUTH_CPD_ID}',  'HubSpot Neverdrop MCP Tool')
        ) AS cpd_data(id, component_name)
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
    # VarNode expressions store the variable name; we look up the OrgVariableDefinition
    # to recover the definition UUID that the old BasicParameter held.
    bind.execute(
        sa.text("""
        WITH source AS (
            SELECT
                ipi.id                          AS ipi_id,
                pi.component_instance_id,
                pi.name                         AS param_name,
                ovd.id::text                    AS definition_id,
                cpd.id                          AS param_def_id
            FROM input_port_instances ipi
            JOIN port_instances pi ON pi.id = ipi.id
            JOIN field_expressions fe
              ON ipi.field_expression_id = fe.id
            JOIN component_parameter_definitions cpd
              ON cpd.name = pi.name
             AND cpd.id = ANY(ARRAY[
                    :gmail_v2_def_id              ::uuid,
                    :slack_def_id                 ::uuid,
                    :hubspot_mcp_def_id           ::uuid,
                    :hubspot_neverdrop_mcp_def_id ::uuid
                 ])
            JOIN org_variable_definitions ovd
              ON ovd.name = fe.expression_json->>'name'
             AND ovd.type = 'oauth'
            WHERE pi.name = 'oauth_connection_id'
              AND pi.port_definition_id IS NULL
              AND fe.expression_json->>'type' = 'var'
        ),
        restore_bp AS (
            INSERT INTO basic_parameters (id, component_instance_id, parameter_definition_id, value)
            SELECT gen_random_uuid(), component_instance_id, param_def_id, definition_id
            FROM source
            ON CONFLICT DO NOTHING
        )
        DELETE FROM port_instances
        WHERE id IN (SELECT ipi_id FROM source)
    """),
        {
            "gmail_v2_def_id": GMAIL_V2_OAUTH_CPD_ID,
            "slack_def_id": SLACK_OAUTH_CPD_ID,
            "hubspot_mcp_def_id": HUBSPOT_MCP_OAUTH_CPD_ID,
            "hubspot_neverdrop_mcp_def_id": HUBSPOT_NEVERDROP_MCP_OAUTH_CPD_ID,
        },
    )
