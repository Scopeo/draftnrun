"""create traces schema and migrate data

Revision ID: 8729faf18d1c
Revises: 26682b086df6
Create Date: 2025-11-10 15:54:03.957667

"""

from typing import Sequence, Union
import logging
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.dialects.postgresql import JSONB

from settings import settings

LOGGER = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "8729faf18d1c"
down_revision: Union[str, None] = "26682b086df6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the traces schema
    op.execute("CREATE SCHEMA IF NOT EXISTS traces")

    # Create enum types
    # env_type and call_type will be created in public schema (shared with other tables)
    # Only traces-specific types will be created in traces schema

    # Drop types from public schema if they exist (from old ada_traces migration)
    # Only drop the types that are specific to traces
    op.execute("DROP TYPE IF EXISTS public.open_inference_span_kind_values CASCADE")
    op.execute("DROP TYPE IF EXISTS public.statuscode CASCADE")

    call_type_enum = sa.Enum("api", "sandbox", "qa", name="call_type")

    # Create only the types specific to traces in traces schema
    # First, try to drop the types if they exist (they might be orphaned from a previous failed migration)
    # Check both public and traces schemas
    op.execute("DROP TYPE IF EXISTS public.open_inference_span_kind_values CASCADE")
    op.execute("DROP TYPE IF EXISTS public.statuscode CASCADE")
    op.execute("DROP TYPE IF EXISTS traces.open_inference_span_kind_values CASCADE")
    op.execute("DROP TYPE IF EXISTS traces.statuscode CASCADE")

    span_kind_enum = sa.Enum(
        "TOOL",
        "CHAIN",
        "LLM",
        "RETRIEVER",
        "EMBEDDING",
        "AGENT",
        "RERANKER",
        "UNKNOWN",
        "GUARDRAIL",
        "EVALUATOR",
        name="open_inference_span_kind_values",
        schema="traces",
    )
    statuscode_enum = sa.Enum("UNSET", "OK", "ERROR", name="statuscode", schema="traces")

    # Create the spans table
    op.create_table(
        "spans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_rowid", sa.String(), nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("parent_id", sa.String(), nullable=True),
        sa.Column("graph_runner_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("span_kind", span_kind_enum, nullable=False),
        sa.Column("start_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("end_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attributes", JSONB(), nullable=False),
        sa.Column("events", sa.Text(), nullable=False),
        sa.Column("status_code", statuscode_enum, server_default="UNSET", nullable=False),
        sa.Column("status_message", sa.String(), nullable=True),
        sa.Column("cumulative_error_count", sa.Integer(), nullable=False),
        sa.Column("cumulative_llm_token_count_prompt", sa.Integer(), nullable=False),
        sa.Column("cumulative_llm_token_count_completion", sa.Integer(), nullable=False),
        sa.Column("llm_token_count_prompt", sa.Integer(), nullable=True),
        sa.Column("llm_token_count_completion", sa.Integer(), nullable=True),
        sa.Column("environment", sa.String(), nullable=True),  # Will be altered to env_type after table creation
        sa.Column("call_type", call_type_enum, nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("tag_name", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("span_id"),
        schema="traces",
    )

    # Create indexes for spans table
    op.create_index(op.f("ix_traces_spans_trace_rowid"), "spans", ["trace_rowid"], unique=False, schema="traces")
    op.create_index(op.f("ix_traces_spans_parent_id"), "spans", ["parent_id"], unique=False, schema="traces")
    op.create_index(
        op.f("ix_traces_spans_graph_runner_id"), "spans", ["graph_runner_id"], unique=False, schema="traces"
    )
    op.create_index(op.f("ix_traces_spans_start_time"), "spans", ["start_time"], unique=False, schema="traces")
    op.create_index(op.f("ix_traces_spans_project_id"), "spans", ["project_id"], unique=False, schema="traces")

    # Alter the environment column to use env_type enum (it already exists, so we need to alter it)
    op.execute("ALTER TABLE traces.spans ALTER COLUMN environment TYPE env_type USING environment::env_type")

    # Create the organization_usage table
    op.create_table(
        "organization_usage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="traces",
    )

    # Create index for organization_usage table
    op.create_index(
        op.f("ix_traces_organization_usage_organization_id"),
        "organization_usage",
        ["organization_id"],
        unique=False,
        schema="traces",
    )

    # Create the span_messages table
    op.create_table(
        "span_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("span_id", sa.String(), nullable=False),
        sa.Column("input_content", sa.Text(), nullable=False),
        sa.Column("output_content", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="traces",
    )

    # Migrate data from ada_traces database if TRACES_DB_URL is set
    if settings.TRACES_DB_URL:
        LOGGER.info("TRACES_DB_URL is set, attempting to migrate data from ada_traces...")
        connection = op.get_bind()
        source_engine = create_engine(settings.TRACES_DB_URL, echo=False)

        try:
            source_inspector = inspect(source_engine)
            source_tables = source_inspector.get_table_names()
            tables_to_migrate = ["spans", "span_messages", "organization_usage"]

            # Validate all required tables exist before starting migration
            missing_tables = [table for table in tables_to_migrate if table not in source_tables]
            if missing_tables:
                error_msg = f"Required tables not found in source database: {', '.join(missing_tables)}"
                LOGGER.error(error_msg)
                raise ValueError(error_msg)

            with source_engine.connect() as source_conn:
                for table_name in tables_to_migrate:
                    # Get row count from source
                    source_count = source_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                    LOGGER.info(f"Migrating {table_name}: {source_count} rows from source")

                    if source_count == 0:
                        LOGGER.info(f"No data to migrate for {table_name}. Skipping.")
                        continue

                    # Check if destination table already has data
                    dest_count = connection.execute(text(f'SELECT COUNT(*) FROM traces."{table_name}"')).scalar()

                    if dest_count > 0:
                        LOGGER.warning(
                            (
                                f"Destination table traces.{table_name} already has {dest_count} rows. "
                                "Will upsert to avoid duplicates and handle conflicts."
                            )
                        )

                    # Use batch upserts for efficient data migration (INSERT ... ON CONFLICT DO UPDATE)
                    BATCH_SIZE = 1000
                    LOGGER.info(f"  Migrating {table_name} in batches of {BATCH_SIZE}...")

                    if table_name == "spans":
                        # For spans, handle enum conversions
                        query = text(
                            """
                            SELECT
                                id, trace_rowid, span_id, parent_id, graph_runner_id, name,
                                span_kind::text as span_kind, start_time, end_time,
                                attributes::text as attributes, events,
                                status_code::text as status_code, status_message, cumulative_error_count,
                                cumulative_llm_token_count_prompt, cumulative_llm_token_count_completion,
                                llm_token_count_prompt, llm_token_count_completion,
                                environment::text as environment, call_type::text as call_type,
                                project_id, tag_name
                            FROM spans
                            ORDER BY id
                            """
                        )
                        insert_query = text(
                            """
                            INSERT INTO traces.spans (
                                id, trace_rowid, span_id, parent_id, graph_runner_id, name,
                                span_kind, start_time, end_time, attributes, events,
                                status_code, status_message, cumulative_error_count,
                                cumulative_llm_token_count_prompt, cumulative_llm_token_count_completion,
                                llm_token_count_prompt, llm_token_count_completion,
                                environment, call_type, project_id, tag_name
                            ) VALUES (
                                :id, :trace_rowid, :span_id, :parent_id, :graph_runner_id, :name,
                                CAST(:span_kind AS traces.open_inference_span_kind_values),
                                :start_time, :end_time, CAST(:attributes AS jsonb), :events,
                                CAST(:status_code AS traces.statuscode),
                                :status_message, :cumulative_error_count,
                                :cumulative_llm_token_count_prompt, :cumulative_llm_token_count_completion,
                                :llm_token_count_prompt, :llm_token_count_completion,
                                CASE WHEN :environment IS NULL THEN NULL ELSE CAST(:environment AS env_type) END,
                                CASE WHEN :call_type IS NULL THEN NULL ELSE CAST(:call_type AS call_type) END,
                                :project_id, :tag_name
                            )
                            ON CONFLICT (id) DO UPDATE SET
                                trace_rowid = EXCLUDED.trace_rowid,
                                span_id = EXCLUDED.span_id,
                                parent_id = EXCLUDED.parent_id,
                                graph_runner_id = EXCLUDED.graph_runner_id,
                                name = EXCLUDED.name,
                                span_kind = EXCLUDED.span_kind,
                                start_time = EXCLUDED.start_time,
                                end_time = EXCLUDED.end_time,
                                attributes = EXCLUDED.attributes,
                                events = EXCLUDED.events,
                                status_code = EXCLUDED.status_code,
                                status_message = EXCLUDED.status_message,
                                cumulative_error_count = EXCLUDED.cumulative_error_count,
                                cumulative_llm_token_count_prompt = EXCLUDED.cumulative_llm_token_count_prompt,
                                cumulative_llm_token_count_completion = EXCLUDED.cumulative_llm_token_count_completion,
                                llm_token_count_prompt = EXCLUDED.llm_token_count_prompt,
                                llm_token_count_completion = EXCLUDED.llm_token_count_completion,
                                environment = EXCLUDED.environment,
                                call_type = EXCLUDED.call_type,
                                project_id = EXCLUDED.project_id,
                                tag_name = EXCLUDED.tag_name
                            """
                        )
                    elif table_name == "span_messages":
                        query = text(
                            "SELECT id, span_id, input_content, output_content FROM span_messages ORDER BY id"
                        )
                        insert_query = text(
                            """
                            INSERT INTO traces.span_messages (id, span_id, input_content, output_content)
                            VALUES (:id, :span_id, :input_content, :output_content)
                            ON CONFLICT (id) DO UPDATE SET
                                span_id = EXCLUDED.span_id,
                                input_content = EXCLUDED.input_content,
                                output_content = EXCLUDED.output_content
                            """
                        )
                    elif table_name == "organization_usage":
                        query = text("SELECT id, organization_id, total_tokens FROM organization_usage ORDER BY id")
                        insert_query = text(
                            """
                            INSERT INTO traces.organization_usage (id, organization_id, total_tokens)
                            VALUES (:id, :organization_id, :total_tokens)
                            ON CONFLICT (id) DO UPDATE SET
                                organization_id = EXCLUDED.organization_id,
                                total_tokens = EXCLUDED.total_tokens
                            """
                        )

                    # Read and upsert in batches
                    offset = 0
                    total_processed = 0
                    while True:
                        batch_query = text(f"{str(query)} LIMIT {BATCH_SIZE} OFFSET {offset}")
                        rows = source_conn.execute(batch_query).fetchall()

                        if not rows:
                            break

                        # Convert rows to dicts and prepare for batch upsert
                        batch_data = []
                        for row in rows:
                            row_dict = dict(row._mapping)
                            # Handle JSONB attributes - convert string to dict if needed
                            if "attributes" in row_dict:
                                if isinstance(row_dict["attributes"], str):

                                    row_dict["attributes"] = json.loads(row_dict["attributes"])
                                # Convert dict back to JSON string for SQL parameter
                                if isinstance(row_dict["attributes"], dict):

                                    row_dict["attributes"] = json.dumps(row_dict["attributes"])
                            # Handle NULL values for optional enum fields
                            if table_name == "spans":
                                if row_dict.get("environment") is None:
                                    row_dict["environment"] = None
                                if row_dict.get("call_type") is None:
                                    row_dict["call_type"] = None
                            batch_data.append(row_dict)

                        # Batch upsert using executemany for efficiency (INSERT ... ON CONFLICT DO UPDATE)
                        connection.execute(insert_query, batch_data)
                        total_processed += len(batch_data)
                        offset += BATCH_SIZE
                        LOGGER.info(f"  Processed {total_processed}/{source_count} rows (inserted or updated)...")

                    LOGGER.info(f"Completed migration of {table_name}: {total_processed} rows processed")

                    # Verify migration
                    final_count = connection.execute(text(f'SELECT COUNT(*) FROM traces."{table_name}"')).scalar()
                    LOGGER.info(f"Successfully migrated {table_name}: {final_count} rows")

                    # Reset the sequence for tables with auto-incrementing IDs
                    if table_name in ["spans", "span_messages", "organization_usage"] and total_processed > 0:
                        # Get the maximum ID value
                        max_id_result = connection.execute(
                            text(f'SELECT COALESCE(MAX(id), 0) FROM traces."{table_name}"')
                        ).scalar()
                        if max_id_result is not None and max_id_result > 0:
                            # Get the actual sequence name using pg_get_serial_sequence
                            # Format: 'schema.table' (no quotes around schema/table unless needed)
                            sequence_query = text(f"SELECT pg_get_serial_sequence('traces.{table_name}', 'id')")
                            sequence_name_result = connection.execute(sequence_query).scalar()
                            if sequence_name_result:
                                # Set the sequence to the next value after the max ID
                                # The third parameter 'true' means the next call to nextval will return max_id + 1
                                connection.execute(
                                    text(f"SELECT setval('{sequence_name_result}', {max_id_result}, true)")
                                )
                                LOGGER.info(f"  Reset sequence {sequence_name_result} to {max_id_result}")
                            else:
                                LOGGER.warning(f"  Could not find sequence for traces.{table_name}.id")

        except Exception as e:
            LOGGER.error(f"Error during data migration: {e}")
            LOGGER.warning("Migration can be retried by running: alembic upgrade head")
            raise  # Re-raise to mark migration as failed
        finally:
            source_engine.dispose()
    else:
        LOGGER.info("TRACES_DB_URL not set, skipping data migration")


def downgrade() -> None:
    # Drop tables
    op.drop_table("span_messages", schema="traces", if_exists=True)
    op.drop_index(
        op.f("ix_traces_organization_usage_organization_id"),
        table_name="organization_usage",
        schema="traces",
        if_exists=True,
    )
    op.drop_table("organization_usage", schema="traces", if_exists=True)
    op.drop_index(op.f("ix_traces_spans_project_id"), table_name="spans", schema="traces", if_exists=True)
    op.drop_index(op.f("ix_traces_spans_start_time"), table_name="spans", schema="traces", if_exists=True)
    op.drop_index(op.f("ix_traces_spans_graph_runner_id"), table_name="spans", schema="traces", if_exists=True)
    op.drop_index(op.f("ix_traces_spans_parent_id"), table_name="spans", schema="traces", if_exists=True)
    op.drop_index(op.f("ix_traces_spans_trace_rowid"), table_name="spans", schema="traces", if_exists=True)
    op.drop_table("spans", schema="traces", if_exists=True)

    # Drop enum types
    # Note: env_type is in public schema and used by other tables, don't drop it
    op.execute("DROP TYPE IF EXISTS traces.statuscode")
    op.execute("DROP TYPE IF EXISTS traces.open_inference_span_kind_values")

    op.execute("DROP TYPE IF EXISTS public.call_type")

    op.execute("DROP SCHEMA IF EXISTS traces CASCADE")
