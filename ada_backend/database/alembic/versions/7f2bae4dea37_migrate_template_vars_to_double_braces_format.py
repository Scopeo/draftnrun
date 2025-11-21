"""migrate_template_vars_to_double_braces_format

Revision ID: 7f2bae4dea37
Revises: b0ba5107a7e3
Create Date: 2025-01-27 12:00:00.000000

"""

from typing import Sequence, Union
from uuid import UUID

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "7f2bae4dea37"
down_revision: Union[str, None] = "b0ba5107a7e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AI_AGENT_INITIAL_PROMPT_PARAM_ID = UUID("1cd1cd58-f066-4cf5-a0f5-9b2018fc4c6a")
LLM_CALL_PROMPT_TEMPLATE_PARAM_ID = UUID("e79b8f5f-d9cc-4a1f-a98a-4992f42a0196")


def upgrade() -> None:
    connection = op.get_bind()

    table_exists = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'component_parameter_definitions'
            )
            """
        )
    ).scalar()

    if not table_exists:
        return

    params_exist = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1 FROM component_parameter_definitions
                WHERE id IN (:ai_agent_id, :llm_call_id)
            )
            """
        ).bindparams(
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
        )
    ).scalar()

    if not params_exist:
        return

    regex_pattern = r"(?<!@)(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})"
    replacement = r"{{\1}}"

    op.execute(
        text(
            """
            UPDATE component_parameter_definitions
            SET "default" = regexp_replace("default", :pattern, :replacement, 'g')
            WHERE id IN (:ai_agent_id, :llm_call_id)
              AND "default" IS NOT NULL
              AND "default" ~ :pattern_check
            """
        ).bindparams(
            pattern=regex_pattern,
            replacement=replacement,
            pattern_check=regex_pattern,
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
        )
    )


def downgrade() -> None:
    connection = op.get_bind()

    table_exists = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'component_parameter_definitions'
            )
            """
        )
    ).scalar()

    if not table_exists:
        return

    params_exist = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1 FROM component_parameter_definitions
                WHERE id IN (:ai_agent_id, :llm_call_id)
            )
            """
        ).bindparams(
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
        )
    ).scalar()

    if not params_exist:
        return

    regex_pattern = r"(?<!@)\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}"
    replacement = r"{\1}"

    op.execute(
        text(
            """
            UPDATE component_parameter_definitions
            SET "default" = regexp_replace("default", :pattern, :replacement, 'g')
            WHERE id IN (:ai_agent_id, :llm_call_id)
              AND "default" IS NOT NULL
              AND "default" ~ :pattern_check
            """
        ).bindparams(
            pattern=regex_pattern,
            replacement=replacement,
            pattern_check=regex_pattern,
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
        )
    )
