"""add model_capabilities and llm_model param type

Revision ID: 33ba7b38592e
Revises: b0ba5107a7e3
Create Date: 2025-11-18 10:13:32.095392

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "33ba7b38592e"
down_revision: Union[str, None] = "b0ba5107a7e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # Use a raw connection with autocommit for both column addition and enum operations
    raw_connection = connection.connection
    old_isolation = raw_connection.isolation_level
    raw_connection.set_isolation_level(0)  # AUTOCOMMIT

    cursor = raw_connection.cursor()

    # Check if table exists before adding column
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'component_parameter_definitions'
        )
    """
    )
    table_exists = cursor.fetchone()[0]

    if table_exists:
        # Check if column already exists
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'component_parameter_definitions'
                AND column_name = 'model_capabilities'
            )
        """
        )
        column_exists = cursor.fetchone()[0]

        # Add model_capabilities column if it doesn't exist
        if not column_exists:
            cursor.execute("ALTER TABLE component_parameter_definitions ADD COLUMN model_capabilities JSON")

    # Check if enum type exists before trying to add value
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM pg_type
            WHERE typname = 'parameter_type'
        )
    """
    )
    enum_exists = cursor.fetchone()[0]

    # Add llm_model parameter type to the enum if enum exists
    if enum_exists:
        cursor.execute("ALTER TYPE parameter_type ADD VALUE IF NOT EXISTS 'llm_model'")

    cursor.close()

    # Restore the original isolation level
    raw_connection.set_isolation_level(old_isolation)

    # Update existing parameters to use new type and set model_capabilities
    # Only run if table exists (skip for fresh databases)
    if not table_exists:
        return

    # For completion-based components
    connection.execute(
        sa.text(
            """
            UPDATE component_parameter_definitions cpd
            SET type = 'llm_model', model_capabilities = '["completion"]'
            WHERE cpd.name = 'completion_model'
            AND cpd.type = 'string'
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
            AND cpd.type = 'string'
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
            AND cpd.type = 'string'
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
            AND cpd.type = 'string'
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
            AND cpd.type = 'string'
        """
        )
    )

    # Drop the foreign key constraint that was auto-detected
    op.drop_constraint(op.f("span_messages_span_id_fkey"), "span_messages", schema="traces", type_="foreignkey")


def downgrade() -> None:
    connection = op.get_bind()

    # Check if table exists before attempting downgrade
    raw_connection = connection.connection
    old_isolation = raw_connection.isolation_level
    raw_connection.set_isolation_level(0)

    cursor = raw_connection.cursor()
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'component_parameter_definitions'
        )
    """
    )
    table_exists = cursor.fetchone()[0]
    cursor.close()

    raw_connection.set_isolation_level(old_isolation)

    if not table_exists:
        return

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

    # Restore the foreign key constraint
    op.create_foreign_key(
        op.f("span_messages_span_id_fkey"),
        "span_messages",
        "spans",
        ["span_id"],
        ["span_id"],
        source_schema="traces",
        referent_schema="traces",
        ondelete="CASCADE",
    )

    # Drop the model_capabilities column using raw SQL with error handling
    try:
        connection.execute(
            sa.text("ALTER TABLE component_parameter_definitions DROP COLUMN IF EXISTS model_capabilities")
        )
    except Exception:
        pass
