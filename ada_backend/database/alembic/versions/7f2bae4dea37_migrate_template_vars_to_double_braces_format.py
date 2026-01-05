"""migrate_template_vars_to_double_braces_format

Revision ID: 7f2bae4dea37
Revises: 1d0c97757e4d
Create Date: 2025-01-27 12:00:00.000000

"""

from typing import Sequence, Union
from uuid import UUID

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "7f2bae4dea37"
down_revision: Union[str, None] = "f2c95397dc15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AI_AGENT_INITIAL_PROMPT_PARAM_ID = UUID("1cd1cd58-f066-4cf5-a0f5-9b2018fc4c6a")
LLM_CALL_PROMPT_TEMPLATE_PARAM_ID = UUID("e79b8f5f-d9cc-4a1f-a98a-4992f42a0196")
RAG_V2_PROMPT_TEMPLATE_ID = UUID("b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e")
SYNTHESIZER_PROMPT_TEMPLATE_ID = UUID("373dc6d2-e12d-495c-936f-e07d1c27e254")
HYBRID_SYNTHESIZER_PROMPT_TEMPLATE_ID = UUID("78df9f84-2d9c-4499-bafe-24c7c96d2a08")
DOCUMENT_REACT_LOADER_PROMPT_ID = UUID("f70d5b64-72b3-4fc5-a443-6242c58a6a77")


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
                WHERE id IN (
                    :ai_agent_id, :llm_call_id, :rag_v2_id, :synthesizer_id,
                    :hybrid_synthesizer_id, :doc_react_loader_id
                )
            )
            """
        ).bindparams(
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
            rag_v2_id=str(RAG_V2_PROMPT_TEMPLATE_ID),
            synthesizer_id=str(SYNTHESIZER_PROMPT_TEMPLATE_ID),
            hybrid_synthesizer_id=str(HYBRID_SYNTHESIZER_PROMPT_TEMPLATE_ID),
            doc_react_loader_id=str(DOCUMENT_REACT_LOADER_PROMPT_ID),
        )
    ).scalar()

    if not params_exist:
        return

    regex_pattern = r"(?<!@)(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})"
    replacement = r"{{\1}}"

    # Update default values in component_parameter_definitions
    op.execute(
        text(
            """
            UPDATE component_parameter_definitions
            SET "default" = regexp_replace("default", :pattern, :replacement, 'g')
            WHERE id IN (
                :ai_agent_id, :llm_call_id, :rag_v2_id, :synthesizer_id,
                :hybrid_synthesizer_id, :doc_react_loader_id
            )
              AND "default" IS NOT NULL
              AND "default" ~ :pattern_check
            """
        ).bindparams(
            pattern=regex_pattern,
            replacement=replacement,
            pattern_check=regex_pattern,
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
            rag_v2_id=str(RAG_V2_PROMPT_TEMPLATE_ID),
            synthesizer_id=str(SYNTHESIZER_PROMPT_TEMPLATE_ID),
            hybrid_synthesizer_id=str(HYBRID_SYNTHESIZER_PROMPT_TEMPLATE_ID),
            doc_react_loader_id=str(DOCUMENT_REACT_LOADER_PROMPT_ID),
        )
    )

    # Check if basic_parameters table exists
    basic_params_table_exists = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'basic_parameters'
            )
            """
        )
    ).scalar()

    if not basic_params_table_exists:
        return

    # Update actual values in basic_parameters for AI Agent, LLM Call, and RAG prompts
    op.execute(
        text(
            """
            UPDATE basic_parameters
            SET value = regexp_replace(value, :pattern, :replacement, 'g')
            WHERE parameter_definition_id IN (
                :ai_agent_id, :llm_call_id, :rag_v2_id, :synthesizer_id,
                :hybrid_synthesizer_id, :doc_react_loader_id
            )
              AND value IS NOT NULL
              AND value ~ :pattern_check
            """
        ).bindparams(
            pattern=regex_pattern,
            replacement=replacement,
            pattern_check=regex_pattern,
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
            rag_v2_id=str(RAG_V2_PROMPT_TEMPLATE_ID),
            synthesizer_id=str(SYNTHESIZER_PROMPT_TEMPLATE_ID),
            hybrid_synthesizer_id=str(HYBRID_SYNTHESIZER_PROMPT_TEMPLATE_ID),
            doc_react_loader_id=str(DOCUMENT_REACT_LOADER_PROMPT_ID),
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
                WHERE id IN (
                    :ai_agent_id, :llm_call_id, :rag_v2_id, :synthesizer_id,
                    :hybrid_synthesizer_id, :doc_react_loader_id
                )
            )
            """
        ).bindparams(
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
            rag_v2_id=str(RAG_V2_PROMPT_TEMPLATE_ID),
            synthesizer_id=str(SYNTHESIZER_PROMPT_TEMPLATE_ID),
            hybrid_synthesizer_id=str(HYBRID_SYNTHESIZER_PROMPT_TEMPLATE_ID),
            doc_react_loader_id=str(DOCUMENT_REACT_LOADER_PROMPT_ID),
        )
    ).scalar()

    if not params_exist:
        return

    regex_pattern = r"(?<!@)\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}"
    replacement = r"{\1}"

    # Downgrade default values in component_parameter_definitions
    op.execute(
        text(
            """
            UPDATE component_parameter_definitions
            SET "default" = regexp_replace("default", :pattern, :replacement, 'g')
            WHERE id IN (
                :ai_agent_id, :llm_call_id, :rag_v2_id, :synthesizer_id,
                :hybrid_synthesizer_id, :doc_react_loader_id
            )
              AND "default" IS NOT NULL
              AND "default" ~ :pattern_check
            """
        ).bindparams(
            pattern=regex_pattern,
            replacement=replacement,
            pattern_check=regex_pattern,
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
            rag_v2_id=str(RAG_V2_PROMPT_TEMPLATE_ID),
            synthesizer_id=str(SYNTHESIZER_PROMPT_TEMPLATE_ID),
            hybrid_synthesizer_id=str(HYBRID_SYNTHESIZER_PROMPT_TEMPLATE_ID),
            doc_react_loader_id=str(DOCUMENT_REACT_LOADER_PROMPT_ID),
        )
    )

    # Check if basic_parameters table exists
    basic_params_table_exists = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'basic_parameters'
            )
            """
        )
    ).scalar()

    if not basic_params_table_exists:
        return

    # Downgrade actual values in basic_parameters for AI Agent, LLM Call, and RAG prompts
    op.execute(
        text(
            """
            UPDATE basic_parameters
            SET value = regexp_replace(value, :pattern, :replacement, 'g')
            WHERE parameter_definition_id IN (
                :ai_agent_id, :llm_call_id, :rag_v2_id, :synthesizer_id,
                :hybrid_synthesizer_id, :doc_react_loader_id
            )
              AND value IS NOT NULL
              AND value ~ :pattern_check
            """
        ).bindparams(
            pattern=regex_pattern,
            replacement=replacement,
            pattern_check=regex_pattern,
            ai_agent_id=str(AI_AGENT_INITIAL_PROMPT_PARAM_ID),
            llm_call_id=str(LLM_CALL_PROMPT_TEMPLATE_PARAM_ID),
            rag_v2_id=str(RAG_V2_PROMPT_TEMPLATE_ID),
            synthesizer_id=str(SYNTHESIZER_PROMPT_TEMPLATE_ID),
            hybrid_synthesizer_id=str(HYBRID_SYNTHESIZER_PROMPT_TEMPLATE_ID),
            doc_react_loader_id=str(DOCUMENT_REACT_LOADER_PROMPT_ID),
        )
    )
