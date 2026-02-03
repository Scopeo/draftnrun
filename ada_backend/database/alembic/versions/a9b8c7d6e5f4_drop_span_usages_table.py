"""drop span_usages table

Revision ID: a9b8c7d6e5f4
Revises: fe1c665d7821
Create Date: 2026-02-03 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, None] = "fe1c665d7821"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Migrate credits from span_usages table to span attributes, then drop the table.

    This migration:
    1. Copies all existing credits from span_usages into span.attributes as JSONB
    2. Drops the span_usages table

    Credits are now stored in span attributes as:
    - credits.input_token (for LLM token input costs)
    - credits.output_token (for LLM token output costs)
    - credits.per_call (for component per-call costs)
    - credits.per (for future per-unit costs)
    """
    connection = op.get_bind()

    # Migrate existing credits from span_usages to span attributes
    # This preserves all historical credit data
    # Note: Using array notation '{credits, input_token}' creates nested structure {"credits": {"input_token": value}}
    migration_query = text("""
        UPDATE traces.spans s
        SET attributes = jsonb_set(
            jsonb_set(
                jsonb_set(
                    jsonb_set(
                        COALESCE(s.attributes, '{}'::jsonb),
                        '{credits, input_token}',
                        to_jsonb(COALESCE(su.credits_input_token, 0)),
                        true
                    ),
                    '{credits, output_token}',
                    to_jsonb(COALESCE(su.credits_output_token, 0)),
                    true
                ),
                '{credits, per_call}',
                to_jsonb(COALESCE(su.credits_per_call, 0)),
                true
            ),
            '{credits, per}',
            COALESCE(su.credits_per, 'null'::jsonb),
            true
        )
        FROM credits.span_usages su
        WHERE s.span_id = su.span_id
        AND (
            su.credits_input_token IS NOT NULL
            OR su.credits_output_token IS NOT NULL
            OR su.credits_per_call IS NOT NULL
            OR su.credits_per IS NOT NULL
        )
    """)

    connection.execute(migration_query)

    # Drop the index first
    op.drop_index(op.f("ix_credits_span_usages_span_id"), table_name="span_usages", schema="credits")

    # Drop the span_usages table (now that data is migrated)
    op.drop_table("span_usages", schema="credits")


def downgrade() -> None:
    """
    Recreate the span_usages table and migrate data back from span attributes.

    This allows rolling back the migration while preserving credit data.
    """
    # Recreate span_usages table
    op.create_table(
        "span_usages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("credits_input_token", sa.Float(), nullable=True),
        sa.Column("credits_output_token", sa.Float(), nullable=True),
        sa.Column("credits_per_call", sa.Float(), nullable=True),
        sa.Column("credits_per", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["span_id"],
            ["traces.spans.span_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="credits",
    )

    # Recreate the unique index
    op.create_index(op.f("ix_credits_span_usages_span_id"), "span_usages", ["span_id"], unique=True, schema="credits")

    # Migrate data back from span attributes to span_usages table
    connection = op.get_bind()

    rollback_query = text("""
        INSERT INTO credits.span_usages (
            span_id, credits_input_token, credits_output_token, credits_per_call, credits_per
        )
        SELECT
            s.span_id,
            (s.attributes->'credits'->>'input_token')::float,
            (s.attributes->'credits'->>'output_token')::float,
            (s.attributes->'credits'->>'per_call')::float,
            s.attributes->'credits'->'per'
        FROM traces.spans s
        WHERE s.attributes ? 'credits'
    """)

    connection.execute(rollback_query)
