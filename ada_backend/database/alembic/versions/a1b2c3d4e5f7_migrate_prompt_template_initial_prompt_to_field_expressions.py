"""migrate prompt_template, initial_prompt and output_format
from BasicParameter to FieldExpression, and delete the corresponding stale
ComponentParameterDefinition rows (which are now superseded by port definitions).
filtering_json_schema remains a BasicParameter (PARAMETER kind, not INPUT).

Revision ID: a1b2c3d4e5f7
Revises: a1c2e3f4b5d6
Create Date: 2026-02-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "a1c2e3f4b5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Known ComponentParameterDefinition IDs (from seed files) — needed for downgrade.
PROMPT_TEMPLATE_PARAM_DEF_ID = "e79b8f5f-d9cc-4a1f-a98a-4992f42a0196"
INITIAL_PROMPT_PARAM_DEF_ID = "1cd1cd58-f066-4cf5-a0f5-9b2018fc4c6a"
FILTERING_JSON_SCHEMA_PARAM_DEF_ID = "59443366-5b1f-5543-9fc5-57378f9aaf6e"
FILTER_COMPONENT_VERSION_ID = "02468c0b-bc99-44ce-a435-995acc5e2545"
OUTPUT_FORMAT_PARAM_DEF_ID = "e5282ccb-dcaa-4970-93c1-f6ef5018492d"  # AI Agent
LLM_CALL_OUTPUT_FORMAT_PARAM_DEF_ID = "d7ee43ab-80f8-4ee5-ac38-938163933610"  # LLM Call


MIGRATED_PARAM_NAMES = "ARRAY['prompt_template', 'initial_prompt', 'output_format']"

STALE_CPD_IDS = [
    PROMPT_TEMPLATE_PARAM_DEF_ID,
    INITIAL_PROMPT_PARAM_DEF_ID,
    OUTPUT_FORMAT_PARAM_DEF_ID,
    LLM_CALL_OUTPUT_FORMAT_PARAM_DEF_ID,
]
_STALE_CPD_IDS_ARRAY = "ARRAY[" + ", ".join(f"'{i}'::uuid" for i in STALE_CPD_IDS) + "]"


def upgrade() -> None:
    bind = op.get_bind()

    # DISTINCT ON ensures one row per (component_instance_id, param_name) even
    # when duplicate BasicParameter rows exist for the same name, which would
    # otherwise cause "ON CONFLICT DO UPDATE command cannot affect row a second time".
    # The final DELETE removes ALL matching BasicParameter rows (not just the
    # deduplicated ones) so no orphan rows remain.
    bind.execute(
        sa.text(f"""
        WITH source AS (
            SELECT DISTINCT ON (bp.component_instance_id, cpd.name)
                bp.component_instance_id,
                COALESCE(bp.value, '')  AS value,
                cpd.name                AS param_name,
                gen_random_uuid()       AS new_fe_id
            FROM basic_parameters bp
            JOIN component_parameter_definitions cpd
              ON bp.parameter_definition_id = cpd.id
            WHERE cpd.name = ANY({MIGRATED_PARAM_NAMES})
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
        insert_ipi AS (
            INSERT INTO input_port_instances
                (id, component_instance_id, name, port_definition_id, field_expression_id, created_at)
            SELECT
                gen_random_uuid(),
                component_instance_id,
                param_name,
                NULL,
                new_fe_id,
                now()
            FROM source
            ON CONFLICT (component_instance_id, name)
            DO UPDATE SET field_expression_id = EXCLUDED.field_expression_id,
                          port_definition_id   = NULL
        )
        DELETE FROM basic_parameters bp
        USING component_parameter_definitions cpd
        WHERE bp.parameter_definition_id = cpd.id
          AND cpd.name = ANY({MIGRATED_PARAM_NAMES})
    """)
    )

    # Delete the stale ComponentParameterDefinition rows. These parameters are
    # now handled as port definitions (seeded via seed_ports.py from the
    # component's input schema), so the CPD rows are obsolete and their
    # nullable=False constraint causes spurious validation errors.
    bind.execute(
        sa.text(f"""
        DELETE FROM component_parameter_definitions
        WHERE id = ANY({_STALE_CPD_IDS_ARRAY})
    """)
    )

    # Remove the filtering_json_schema input port definition from the Filter component.
    # This field remains a BasicParameter (PARAMETER kind), so it must not exist as
    # a PortDefinition — seed_ports.py is also updated to skip it via disabled_as_input.
    bind.execute(
        sa.text(f"""
        DELETE FROM port_definitions
        WHERE component_version_id = '{FILTER_COMPONENT_VERSION_ID}'::uuid
          AND name = 'filtering_json_schema'
          AND port_type = 'INPUT'
    """)
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Re-create the CPD rows that were deleted in upgrade so the JOIN in the
    # data-restore step below can find them.  component_version_id values are
    # looked up dynamically to avoid hard-coding UUIDs that differ per env.
    # UUIDs are module-level constants (no user input), so f-string interpolation is safe.
    bind.execute(sa.text(f"""
        INSERT INTO component_parameter_definitions
            (id, component_version_id, name, type, nullable, is_advanced)
        SELECT
            cpd_data.id::uuid,
            cv.id,
            cpd_data.param_name,
            'string'::parameter_type,
            FALSE,
            FALSE
        FROM (VALUES
            ('{PROMPT_TEMPLATE_PARAM_DEF_ID}',       'AI',       'prompt_template'),
            ('{INITIAL_PROMPT_PARAM_DEF_ID}',         'AI Agent', 'initial_prompt'),
            ('{OUTPUT_FORMAT_PARAM_DEF_ID}',          'AI Agent', 'output_format'),
            ('{LLM_CALL_OUTPUT_FORMAT_PARAM_DEF_ID}', 'AI',       'output_format')
        ) AS cpd_data(id, component_name, param_name)
        CROSS JOIN LATERAL (
            SELECT cv2.id
            FROM component_versions cv2
            JOIN components c ON c.id = cv2.component_id
            WHERE c.name = cpd_data.component_name
            LIMIT 1
        ) AS cv(id)
        ON CONFLICT (id) DO NOTHING
    """))

    # Restore BasicParameter rows from InputPortInstance + FieldExpression.
    # Only literal expressions can be converted back; injected (ref/concat) values are left as-is.
    bind.execute(
        sa.text("""
        WITH source AS (
            SELECT
                ipi.id                          AS ipi_id,
                ipi.component_instance_id,
                ipi.name                        AS param_name,
                fe.expression_json->>'value'    AS literal_value,
                cpd.id                          AS param_def_id
            FROM input_port_instances ipi
            JOIN field_expressions fe
              ON ipi.field_expression_id = fe.id
            JOIN component_parameter_definitions cpd
              ON cpd.name = ipi.name
             AND cpd.id = ANY(ARRAY[
                    :prompt_template_def_id      ::uuid,
                    :initial_prompt_def_id       ::uuid,
                    :output_format_def_id               ::uuid,
                    :llm_call_output_format_def_id      ::uuid
                 ])
            WHERE ipi.name  = ANY(ARRAY['prompt_template', 'initial_prompt', 'output_format'])
              AND ipi.port_definition_id IS NULL
              AND fe.expression_json->>'type' = 'literal'
        ),
        restore_bp AS (
            INSERT INTO basic_parameters (id, component_instance_id, parameter_definition_id, value)
            SELECT gen_random_uuid(), component_instance_id, param_def_id, literal_value
            FROM source
            ON CONFLICT DO NOTHING
        )
        DELETE FROM input_port_instances
        WHERE id IN (SELECT ipi_id FROM source)
    """),
        {
            "prompt_template_def_id": PROMPT_TEMPLATE_PARAM_DEF_ID,
            "initial_prompt_def_id": INITIAL_PROMPT_PARAM_DEF_ID,
            "output_format_def_id": OUTPUT_FORMAT_PARAM_DEF_ID,
            "llm_call_output_format_def_id": LLM_CALL_OUTPUT_FORMAT_PARAM_DEF_ID,
        },
    )
