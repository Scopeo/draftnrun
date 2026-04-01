"""Migrate completion_model from BasicParameter to FieldExpression + InputPortInstance.

Creates INPUT PortDefinitions for completion_model on 10 migrated component versions
and migrates existing BasicParameter rows to FieldExpression LiteralNodes + InputPortInstances.
Unmigrated components (Synthesizer, HybridSynthesizer, RelevantChunkSelector) keep
completion_model as a BasicParameter.

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-03-24 00:00:00.000000

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
deploy_strategy: Union[str, None] = "breaking"

COMPLETION_MODEL_CPD_IDS = [
    "e2d157b4-f26d-41b4-9e47-62b5b041a9ff",  # AI Agent
    "1233f6b4-cfab-44f6-bf62-f6e0a1b95db1",  # LLM Call
    "3d6b6263-7ada-4021-bb56-3ee2653e9fb3",  # Categorizer
    "329f22ec-0382-4fcf-963f-3281e68e6222",  # Web Search (OpenAI)
    "978afae2-4a79-4f26-a3a1-0a64cbd75b82",  # SQL Tool
    "329f22ec-0382-4fcf-963f-3281e68e6224",  # OCR Call
    "12345678-9012-3456-7890-123456789012",  # ReAct SQL
    "134a4ddb-6906-4a22-b6b9-404f48543cc7",  # RAG Agent v3
    "69ae956a-31f0-4349-8d87-115fd42c3356",  # Smart RAG (Document React Loader)
    "a1b2c3d4-e5f6-7890-abcd-ef1234567890",  # DOCX Template Agent
]

CPD_IDS_ARRAY = "ARRAY[" + ", ".join(f"'{uid}'::uuid" for uid in COMPLETION_MODEL_CPD_IDS) + "]"

DEFAULT_MODEL = "anthropic:claude-haiku-4-5"

DEFAULT_MODEL_WEB_SEARCH = "openai:gpt-5-mini"
DEFAULT_MODEL_OCR = "mistral:mistral-ocr-latest"

CAP_COMPLETION = "completion"
CAP_FUNCTION_CALLING = "function_calling"
CAP_WEB_SEARCH = "web_search"
CAP_OCR = "ocr"

COMPONENT_VERSIONS = [
    (
        "22292e7f-a3ba-4c63-a4c7-dd5c0c75cdaa",
        "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e5f6",
        DEFAULT_MODEL,
        CAP_FUNCTION_CALLING,
    ),
    ("7a039611-49b3-4bfd-b09b-c0f93edf3b79", "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e5f7", DEFAULT_MODEL, CAP_COMPLETION),
    ("c4a1e2f3-5d6b-4c7a-8e9f-1a2b3c4d5e6f", "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e5f8", DEFAULT_MODEL, CAP_COMPLETION),
    (
        "d6020df0-a7e0-4d82-b731-0a653beef2e5",
        "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e5f9",
        DEFAULT_MODEL_WEB_SEARCH,
        CAP_WEB_SEARCH,
    ),
    ("f7ddbfcb-6843-4ae9-a15b-40aa565b955b", "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e5fa", DEFAULT_MODEL, CAP_COMPLETION),
    ("a3b4c5d6-e7f8-9012-3456-789abcdef012", "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e5fb", DEFAULT_MODEL_OCR, CAP_OCR),
    (
        "d0e83ab2-fed1-4e32-9347-0c41353f3eb8",
        "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e5fc",
        DEFAULT_MODEL,
        CAP_FUNCTION_CALLING,
    ),
    ("f1a5b6c7-d8e9-4f0a-1b2c-3d4e5f6a7b8c", "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e5fd", DEFAULT_MODEL, CAP_COMPLETION),
    (
        "1c2fdf5b-4a8d-4788-acb6-86b00124c7ce",
        "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e601",
        DEFAULT_MODEL,
        CAP_FUNCTION_CALLING,
    ),
    (
        "e2b30000-3333-4444-5555-666666666666",
        "d1e2f3a4-b5c6-4d7e-8f90-a1b2c3d4e602",
        DEFAULT_MODEL,
        CAP_FUNCTION_CALLING,
    ),
]

PORT_DEF_IDS = [pd_id for _, pd_id, _, _ in COMPONENT_VERSIONS]
PORT_DEF_IDS_ARRAY = "ARRAY[" + ", ".join(f"'{uid}'::uuid" for uid in PORT_DEF_IDS) + "]"

COMPONENT_VERSION_IDS = [cv_id for cv_id, _, _, _ in COMPONENT_VERSIONS]
CV_IDS_ARRAY = "ARRAY[" + ", ".join(f"'{uid}'::uuid" for uid in COMPONENT_VERSION_IDS) + "]"


def upgrade() -> None:
    bind = op.get_bind()

    rows_before = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM basic_parameters WHERE parameter_definition_id = ANY({CPD_IDS_ARRAY})"),
    ).scalar()

    for cv_id, pd_id, default_model, capability in COMPONENT_VERSIONS:
        ui_props = json.dumps({"label": "Model Name", "model_capabilities": [capability]})
        bind.execute(
            sa.text(f"""
                INSERT INTO port_definitions (
                    id, component_version_id, name, port_type, is_canonical,
                    description, parameter_type, ui_component, ui_component_properties,
                    nullable, "default", is_tool_input, is_advanced, drives_output_schema
                )
                SELECT
                    '{pd_id}'::uuid,
                    '{cv_id}'::uuid,
                    'completion_model',
                    'INPUT'::port_type,
                    false,
                    'The LLM model to use for this component.',
                    'llm_model'::parameter_type,
                    'Select'::ui_component,
                    CAST(:ui_props AS jsonb),
                    false,
                    :default_model,
                    false,
                    false,
                    false
                WHERE EXISTS (
                    SELECT 1 FROM component_versions WHERE id = '{cv_id}'::uuid
                )
                ON CONFLICT ON CONSTRAINT unique_component_version_port DO NOTHING
            """),
            {"ui_props": ui_props, "default_model": default_model},
        )

    bind.execute(
        sa.text(f"""
            WITH source AS (
                SELECT DISTINCT ON (bp.component_instance_id)
                    bp.component_instance_id,
                    COALESCE(bp.value, cpd."default")  AS value,
                    gen_random_uuid()                   AS new_fe_id,
                    gen_random_uuid()                   AS new_pi_id
                FROM basic_parameters bp
                JOIN component_parameter_definitions cpd ON bp.parameter_definition_id = cpd.id
                JOIN component_instances ci ON ci.id = bp.component_instance_id
                WHERE bp.parameter_definition_id = ANY({CPD_IDS_ARRAY})
                  AND ci.component_version_id = ANY({CV_IDS_ARRAY})
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
                    source.new_pi_id,
                    source.component_instance_id,
                    'completion_model',
                    pd.id,
                    'INPUT'::port_type,
                    now()
                FROM source
                JOIN component_instances ci ON ci.id = source.component_instance_id
                JOIN port_definitions pd
                    ON pd.component_version_id = ci.component_version_id
                    AND pd.name = 'completion_model'
                    AND pd.port_type = 'INPUT'::port_type
                ON CONFLICT ON CONSTRAINT uq_port_instance_name
                DO UPDATE SET port_definition_id = EXCLUDED.port_definition_id
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
            WHERE parameter_definition_id = ANY({CPD_IDS_ARRAY})
        """),
    )

    bind.execute(
        sa.text(f"DELETE FROM component_parameter_definitions WHERE id = ANY({CPD_IDS_ARRAY})"),
    )

    any_cv_exists = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM component_versions WHERE id = ANY("
            + "ARRAY["
            + ", ".join(f"'{cv}'::uuid" for cv, _, _, _ in COMPONENT_VERSIONS)
            + "]"
            + "))"
        ),
    ).scalar()
    _assert_upgrade_succeeded(bind, rows_before, any_cv_exists)


def _assert_upgrade_succeeded(bind, rows_before: int, any_cv_exists: bool) -> None:
    remaining_bp = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM basic_parameters WHERE parameter_definition_id = ANY({CPD_IDS_ARRAY})"),
    ).scalar()
    if remaining_bp != 0:
        raise RuntimeError(
            f"[e5f6a7b8c9d0] upgrade: {remaining_bp} basic_parameters rows still exist for completion_model CPDs"
        )

    if any_cv_exists:
        pd_count = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM port_definitions WHERE id = ANY({PORT_DEF_IDS_ARRAY})"),
        ).scalar()
        if pd_count == 0:
            raise RuntimeError("[e5f6a7b8c9d0] upgrade: no PortDefinitions created for completion_model")

    migrated_count = bind.execute(
        sa.text(f"""
            SELECT COUNT(*)
            FROM input_port_instances ipi
            JOIN port_instances pi ON pi.id = ipi.id
            WHERE pi.name = 'completion_model'
              AND pi.port_definition_id = ANY({PORT_DEF_IDS_ARRAY})
        """),
    ).scalar()
    if rows_before > 0 and migrated_count != rows_before:
        raise RuntimeError(
            f"[e5f6a7b8c9d0] upgrade: expected {rows_before} input_port_instances for completion_model, "
            f"got {migrated_count}."
        )


def downgrade() -> None:
    bind = op.get_bind()

    for cpd_id, (cv_id, pd_id, default_model, cap) in zip(COMPLETION_MODEL_CPD_IDS, COMPONENT_VERSIONS):
        bind.execute(
            sa.text(f"""
                INSERT INTO component_parameter_definitions
                    (id, component_version_id, name, type, nullable, "default",
                     ui_component, ui_component_properties, is_advanced, model_capabilities)
                SELECT
                    '{cpd_id}'::uuid,
                    '{cv_id}'::uuid,
                    'completion_model',
                    'llm_model'::parameter_type,
                    false,
                    :default_model,
                    'Select'::ui_component,
                    CAST(:ui_props AS jsonb),
                    false,
                    CAST(:model_caps AS jsonb)
                WHERE EXISTS (
                    SELECT 1 FROM component_versions WHERE id = '{cv_id}'::uuid
                )
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "default_model": default_model,
                "ui_props": json.dumps({"label": "Model Name"}),
                "model_caps": json.dumps([cap]),
            },
        )

    bind.execute(
        sa.text(f"""
            WITH source AS (
                SELECT
                    ipi.id                          AS ipi_id,
                    ipi.field_expression_id          AS fe_id,
                    pi.component_instance_id,
                    fe.expression_json->>'value'    AS literal_value,
                    ci.component_version_id
                FROM input_port_instances ipi
                JOIN port_instances pi ON pi.id = ipi.id
                JOIN field_expressions fe ON ipi.field_expression_id = fe.id
                JOIN component_instances ci ON ci.id = pi.component_instance_id
                WHERE pi.name = 'completion_model'
                  AND pi.port_definition_id = ANY({PORT_DEF_IDS_ARRAY})
                  AND fe.expression_json->>'type' = 'literal'
            ),
            cpd_lookup AS (
                SELECT id AS cpd_id, component_version_id
                FROM component_parameter_definitions
                WHERE name = 'completion_model'
            ),
            restore_bp AS (
                INSERT INTO basic_parameters (id, component_instance_id, parameter_definition_id, value)
                SELECT gen_random_uuid(), source.component_instance_id, cpd_lookup.cpd_id, source.literal_value
                FROM source
                JOIN cpd_lookup ON cpd_lookup.component_version_id = source.component_version_id
                ON CONFLICT DO NOTHING
            ),
            delete_ports AS (
                DELETE FROM port_instances
                WHERE id IN (SELECT ipi_id FROM source)
            )
            DELETE FROM field_expressions
            WHERE id IN (SELECT fe_id FROM source)
        """),
    )

    bind.execute(
        sa.text(f"DELETE FROM port_definitions WHERE id = ANY({PORT_DEF_IDS_ARRAY})"),
    )
