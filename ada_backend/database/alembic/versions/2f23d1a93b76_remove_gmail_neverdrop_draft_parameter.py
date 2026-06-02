"""Remove Gmail Neverdrop draft parameter.

Revision ID: 2f23d1a93b76
Revises: k1l2m3n4o5p6
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "2f23d1a93b76"
down_revision: Union[str, None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "code-first"

GMAIL_NEVERDROP_COMPONENT_VERSION_ID = "78b85445-5a79-4ecd-8c31-f849b0b35d9a"
GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID = "bcf88542-bcfc-4075-8d98-57714c8e8f96"
BACKUP_TABLE = "_alembic_2f23d1a93b76_gmail_neverdrop_draft_costs"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS credits.{BACKUP_TABLE} (
            id uuid PRIMARY KEY,
            credits_per jsonb,
            credits_per_call double precision,
            credits_per_input_token double precision,
            credits_per_output_token double precision,
            component_parameter_definition_id uuid NOT NULL,
            parameter_value varchar
        )
    """)
    op.execute(f"""
        INSERT INTO credits.{BACKUP_TABLE} (
            id,
            credits_per,
            credits_per_call,
            credits_per_input_token,
            credits_per_output_token,
            component_parameter_definition_id,
            parameter_value
        )
        SELECT
            parameter_value_costs.id,
            costs.credits_per,
            costs.credits_per_call,
            costs.credits_per_input_token,
            costs.credits_per_output_token,
            parameter_value_costs.component_parameter_definition_id,
            parameter_value_costs.parameter_value
        FROM credits.parameter_value_costs
        JOIN credits.costs ON costs.id = parameter_value_costs.id
        WHERE
            parameter_value_costs.component_parameter_definition_id =
                '{GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID}'::uuid
        ON CONFLICT (id) DO NOTHING
    """)
    op.execute(f"""
        DELETE FROM basic_parameters
        WHERE parameter_definition_id = '{GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID}'::uuid
    """)
    op.execute(f"""
        DELETE FROM credits.parameter_value_costs
        WHERE component_parameter_definition_id = '{GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID}'::uuid
    """)
    op.execute(f"""
        DELETE FROM credits.costs
        WHERE id IN (SELECT id FROM credits.{BACKUP_TABLE})
    """)
    op.execute(f"""
        DELETE FROM component_parameter_definitions
        WHERE id = '{GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID}'::uuid
    """)


def downgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS credits.{BACKUP_TABLE} (
            id uuid PRIMARY KEY,
            credits_per jsonb,
            credits_per_call double precision,
            credits_per_input_token double precision,
            credits_per_output_token double precision,
            component_parameter_definition_id uuid NOT NULL,
            parameter_value varchar
        )
    """)
    op.execute(f"""
        INSERT INTO component_parameter_definitions (
            id,
            component_version_id,
            name,
            type,
            nullable,
            "default",
            ui_component,
            ui_component_properties,
            is_advanced
        )
        VALUES (
            '{GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID}'::uuid,
            '{GMAIL_NEVERDROP_COMPONENT_VERSION_ID}'::uuid,
            'save_as_draft',
            'boolean',
            FALSE,
            'true',
            'Checkbox',
            json_build_object(
                'label',
                'Save as Draft',
                'description',
                'If checked, the email will be saved as a draft instead of being sent immediately.'
            ),
            FALSE
        )
        ON CONFLICT (id) DO NOTHING
    """)
    op.execute(f"""
        INSERT INTO credits.costs (
            id,
            entity_type,
            credits_per,
            credits_per_call,
            credits_per_input_token,
            credits_per_output_token
        )
        SELECT
            id,
            'parameter_value',
            credits_per,
            credits_per_call,
            credits_per_input_token,
            credits_per_output_token
        FROM credits.{BACKUP_TABLE}
        ON CONFLICT (id) DO NOTHING
    """)
    op.execute(f"""
        INSERT INTO credits.parameter_value_costs (
            id,
            component_parameter_definition_id,
            parameter_value
        )
        SELECT
            id,
            component_parameter_definition_id,
            parameter_value
        FROM credits.{BACKUP_TABLE}
        ON CONFLICT (id) DO NOTHING
    """)
    op.execute(f"DROP TABLE IF EXISTS credits.{BACKUP_TABLE}")
