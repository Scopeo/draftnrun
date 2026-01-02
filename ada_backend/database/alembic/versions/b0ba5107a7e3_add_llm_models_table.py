"""add llm models table and model_capabilities

Revision ID: b0ba5107a7e3
Revises: e2789dbf6d68
Create Date: 2025-11-13 10:51:54.913356

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b0ba5107a7e3"
down_revision: Union[str, None] = "e2789dbf6d68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create llm_models table
    op.create_table(
        "llm_models",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("model_capacity", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_models_id"), "llm_models", ["id"], unique=False)
    llm_models_table = sa.table(
        "llm_models",
        sa.column("display_name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("provider", sa.String()),
        sa.column("model_name", sa.String()),
        sa.column("model_capacity", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.bulk_insert(
        llm_models_table,
        [
            {
                "display_name": "GPT-5",
                "description": None,
                "provider": "openai",
                "model_name": "gpt-5",
                "model_capacity": [
                    "completion",
                    "file",
                    "image",
                    "constrained_output",
                    "function_calling",
                    "web_search",
                    "reasoning",
                ],
            },
            {
                "display_name": "GPT-5 Nano",
                "description": None,
                "provider": "openai",
                "model_name": "gpt-5-nano",
                "model_capacity": [
                    "completion",
                    "file",
                    "image",
                    "constrained_output",
                    "function_calling",
                    "web_search",
                    "reasoning",
                ],
            },
            {
                "display_name": "GPT-5 Mini",
                "description": None,
                "provider": "openai",
                "model_name": "gpt-5-mini",
                "model_capacity": [
                    "completion",
                    "file",
                    "image",
                    "constrained_output",
                    "function_calling",
                    "web_search",
                    "reasoning",
                ],
            },
            {
                "display_name": "GPT-4.1",
                "description": None,
                "provider": "openai",
                "model_name": "gpt-4.1",
                "model_capacity": [
                    "completion",
                    "file",
                    "image",
                    "constrained_output",
                    "function_calling",
                    "web_search",
                ],
            },
            {
                "display_name": "GPT-4.1 Mini",
                "description": None,
                "provider": "openai",
                "model_name": "gpt-4.1-mini",
                "model_capacity": [
                    "completion",
                    "file",
                    "image",
                    "constrained_output",
                    "function_calling",
                    "web_search",
                ],
            },
            {
                "display_name": "GPT-4.1 Nano",
                "description": None,
                "provider": "openai",
                "model_name": "gpt-4.1-nano",
                "model_capacity": [
                    "completion",
                    "image",
                    "file",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "GPT-4o",
                "description": None,
                "provider": "openai",
                "model_name": "gpt-4o",
                "model_capacity": [
                    "completion",
                    "image",
                    "file",
                    "constrained_output",
                    "function_calling",
                    "web_search",
                ],
            },
            {
                "display_name": "GPT-4o Mini",
                "description": None,
                "provider": "openai",
                "model_name": "gpt-4o-mini",
                "model_capacity": [
                    "completion",
                    "image",
                    "file",
                    "constrained_output",
                    "function_calling",
                    "web_search",
                ],
            },
            {
                "display_name": "Gemini 2.5 Pro",
                "description": None,
                "provider": "google",
                "model_name": "gemini-2.5-pro-preview-06-05",
                "model_capacity": [
                    "completion",
                    "image",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "Gemini 2.5 Flash",
                "description": None,
                "provider": "google",
                "model_name": "gemini-2.5-flash-preview-05-20",
                "model_capacity": [
                    "completion",
                    "image",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "Gemini 2.0 Flash",
                "description": None,
                "provider": "google",
                "model_name": "gemini-2.0-flash",
                "model_capacity": [
                    "completion",
                    "image",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "Gemini 2.0 Flash lite",
                "description": None,
                "provider": "google",
                "model_name": "gemini-2.0-flash-lite",
                "model_capacity": [
                    "completion",
                    "image",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "Llama 3.3 70B (Cerebras)",
                "description": None,
                "provider": "cerebras",
                "model_name": "llama-3.3-70b",
                "model_capacity": [
                    "completion",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "Qwen 3 235B Instruct (Cerebras)",
                "description": None,
                "provider": "cerebras",
                "model_name": "qwen-3-235b-a22b-instruct-2507",
                "model_capacity": [
                    "completion",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "Qwen 3 32B (Cerebras)",
                "description": None,
                "provider": "cerebras",
                "model_name": "qwen-3-32b",
                "model_capacity": [
                    "completion",
                    "constrained_output",
                    "function_calling",
                    "reasoning",
                ],
            },
            {
                "display_name": "OpenAI GPT OSS (Cerebras)",
                "description": None,
                "provider": "cerebras",
                "model_name": "gpt-oss-120b",
                "model_capacity": [
                    "completion",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "Mistral Large 2411",
                "description": None,
                "provider": "mistral",
                "model_name": "mistral-large-latest",
                "model_capacity": [
                    "completion",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "Mistral Medium 2505",
                "description": None,
                "provider": "mistral",
                "model_name": "mistral-medium-latest",
                "model_capacity": [
                    "completion",
                    "constrained_output",
                    "function_calling",
                ],
            },
            {
                "display_name": "Mistral OCR 2505",
                "description": None,
                "provider": "mistral",
                "model_name": "mistral-ocr-latest",
                "model_capacity": [
                    "ocr",
                ],
            },
            {
                "display_name": "Text Embedding 3 Large",
                "description": None,
                "provider": "openai",
                "model_name": "text-embedding-3-large",
                "model_capacity": [
                    "embedding",
                ],
            },
        ],
    )

    # Add model_capabilities column and llm_model parameter type
    connection = op.get_bind()

    # Check if table exists before adding column
    table_exists = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'component_parameter_definitions'
            )
        """
        )
    ).scalar()

    if table_exists:
        # Check if column already exists
        column_exists = connection.execute(
            sa.text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'component_parameter_definitions'
                    AND column_name = 'model_capabilities'
                )
            """
            )
        ).scalar()

        # Add model_capabilities column if it doesn't exist
        if not column_exists:
            with op.get_context().autocommit_block():
                connection.execute(
                    sa.text("ALTER TABLE component_parameter_definitions ADD COLUMN model_capabilities JSONB")
                )

    # Check if enum type exists before trying to add value
    enum_exists = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT FROM pg_type
                WHERE typname = 'parameter_type'
            )
        """
        )
    ).scalar()

    # Add llm_model parameter type to the enum if enum exists
    if enum_exists:
        # ALTER TYPE ... ADD VALUE must run outside a transaction block on Postgres
        with op.get_context().autocommit_block():
            connection.execute(sa.text("ALTER TYPE parameter_type ADD VALUE IF NOT EXISTS 'llm_model'"))

    # Update existing parameters to use new type and set model_capabilities
    # Only run if table exists (skip for fresh databases)
    if table_exists:
        # For completion-based components
        connection.execute(
            sa.text(
                """
                UPDATE component_parameter_definitions cpd
                SET type = 'llm_model', model_capabilities = '["completion"]'
                WHERE cpd.name = 'completion_model'
                AND cpd.component_version_id IN (
                    '7a039611-49b3-4bfd-b09b-c0f93edf3b79',  -- llm_call
                    '6f790dd1-06f6-4489-a655-1a618763a114',  -- synthesizer
                    '303ff9a5-3264-472c-b69f-c2da5be3bac8',  -- hybrid_synthesizer
                    '079512c6-28e2-455f-af2c-f196015534bd',  -- formatter
                    '1F7334BE-7164-4440-BBF3-E986EED0388F',  -- static_responder
                    '6460b304-640c-4468-abd3-67bbff6902d4',  -- document_enhanced_llm_call_agent
                    '5d9f0f3e-2b4c-5678-9012-345678901bcd'   -- chunk_processor
                )
            """
            )
        )

        # For function calling agents
        connection.execute(
            sa.text(
                """
                UPDATE component_parameter_definitions cpd
                SET type = 'llm_model', model_capabilities = '["function_calling"]'
                WHERE cpd.name = 'completion_model'
                AND cpd.component_version_id IN (
                    '22292e7f-a3ba-4c63-a4c7-dd5c0c75cdaa',  -- base_ai_agent
                    'fe26eac8-61c6-4158-a571-61fd680676c8',  -- rag_agent
                    '69ce9852-00cb-4c9d-86fe-8b8926afa994',  -- hybrid_rag_agent
                    '449f8f59-7aff-4b2d-b244-d2fcc09f6651',  -- tavily_agent
                    'c0f1a2b3-4d5e-6f7a-8b9c-0d1e2f3a4b5c',  -- react_sql_agent
                    'd0e83ab2-fed1-4e32-9347-0c41353f3eb8',  -- react_sql_agent_v2
                    '1c2fdf5b-4a8d-4788-acb6-86b00124c7ce'   -- document_react_loader_agent
                )
            """
            )
        )

        # For web search agents (all versions)
        connection.execute(
            sa.text(
                """
                UPDATE component_parameter_definitions cpd
                SET type = 'llm_model', model_capabilities = '["web_search"]'
                WHERE cpd.name = 'completion_model'
                AND cpd.component_version_id IN (
                    'd6020df0-a7e0-4d82-b731-0a653beef2e6',  -- web_search_openai_agent
                    'd6020df0-a7e0-4d82-b731-0a653beef2e5'   -- web_search_openai_agent_v2
                )
            """
            )
        )

        # For OCR components
        connection.execute(
            sa.text(
                """
                UPDATE component_parameter_definitions cpd
                SET type = 'llm_model', model_capabilities = '["ocr"]'
                WHERE cpd.name = 'completion_model'
                AND cpd.component_version_id = 'a3b4c5d6-e7f8-9012-3456-789abcdef012'  -- ocr_call
            """
            )
        )

        # For embedding models
        connection.execute(
            sa.text(
                """
                UPDATE component_parameter_definitions cpd
                SET type = 'llm_model', model_capabilities = '["embedding"]'
                WHERE cpd.name = 'embedding_model'
            """
            )
        )


def downgrade() -> None:
    connection = op.get_bind()

    # Check if table exists before attempting downgrade
    table_exists = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'component_parameter_definitions'
            )
        """
        )
    ).scalar()

    if table_exists:
        # Revert all LLM model parameter types back to STRING
        connection.execute(
            sa.text(
                """
                UPDATE component_parameter_definitions
                SET type = 'string'
                WHERE type = 'llm_model'
            """
            )
        )

        # Drop the model_capabilities column using raw SQL with error handling
        try:
            connection.execute(
                sa.text("ALTER TABLE component_parameter_definitions DROP COLUMN IF EXISTS model_capabilities")
            )
        except Exception:
            pass

    # Drop llm_models table
    op.drop_index(op.f("ix_llm_models_id"), table_name="llm_models")
    op.drop_table("llm_models")
