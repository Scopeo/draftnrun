"""Remove Gmail Neverdrop draft parameter.

Revision ID: l1m2n3o4p5q6
Revises: k1l2m3n4o5p6
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "code-first"

GMAIL_NEVERDROP_COMPONENT_VERSION_ID = "78b85445-5a79-4ecd-8c31-f849b0b35d9a"
GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID = "bcf88542-bcfc-4075-8d98-57714c8e8f96"


def upgrade() -> None:
    op.execute(f"""
        DELETE FROM basic_parameters
        WHERE parameter_definition_id = '{GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID}'::uuid
    """)
    op.execute(f"""
        DELETE FROM credits.parameter_value_costs
        WHERE component_parameter_definition_id = '{GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID}'::uuid
    """)
    op.execute(f"""
        DELETE FROM component_parameter_definitions
        WHERE id = '{GMAIL_NEVERDROP_SAVE_AS_DRAFT_PARAM_ID}'::uuid
    """)


def downgrade() -> None:
    op.execute(f"""
        INSERT INTO component_parameter_definitions (
            id,
            component_version_id,
            name,
            type,
            nullable,
            default,
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
