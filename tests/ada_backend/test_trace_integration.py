import pytest

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace.status import StatusCode
from openinference.semconv.trace import SpanAttributes

from engine.trace.sql_exporter import SQLSpanExporter
from engine.trace.trace_manager import setup_tracer
from settings import settings

import logging
from io import StringIO
import json


@pytest.mark.integration
class TestTraceIntegration:
    """Integration tests for the trace system running against the actual ada_traces database."""

    def test_real_database_connection(self):
        """Test real database connection to ada_traces."""
        from sqlalchemy import create_engine, text

        if not settings.TRACES_DB_URL:
            pytest.skip("TRACES_DB_URL not configured")

        engine = create_engine(settings.TRACES_DB_URL, echo=False)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_sql_exporter_with_real_database(self):
        """Test SQL exporter with the actual ada_traces database."""
        if not settings.TRACES_DB_URL:
            pytest.skip("TRACES_DB_URL not configured")

        try:
            exporter = SQLSpanExporter()
            assert exporter.session is not None

            # Test that we can use the session
            from sqlalchemy import text

            result = exporter.session.execute(text("SELECT 1"))
            assert result.scalar() == 1

        except Exception as e:
            pytest.fail(f"Failed to initialize exporter with real database: {e}")

    def test_span_export_to_real_database(self):
        """Test exporting spans to the actual ada_traces database."""
        if not settings.TRACES_DB_URL:
            pytest.skip("TRACES_DB_URL not configured")

        try:
            exporter = SQLSpanExporter()

            # Create a test span
            tracer_provider = TracerProvider()
            tracer = tracer_provider.get_tracer("integration_test")

            with tracer.start_as_current_span("integration_test_span") as span:
                span.set_attribute("test.attribute", "integration_test_value")
                span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, 15)
                span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, 8)
                span.set_attribute("organization_id", "integration-test-org")

                # Export the span
                result = exporter.export([span])
                assert result.value == 0  # SUCCESS

            # Clean up
            exporter.shutdown()

        except Exception as e:
            pytest.fail(f"Failed to export span to real database: {e}")

    def test_trace_manager_integration(self):
        """Test trace manager with the actual ada_traces database."""
        if not settings.TRACES_DB_URL:
            pytest.skip("TRACES_DB_URL not configured")

        try:
            # Test tracer setup
            tracer, tracer_provider = setup_tracer("integration-test-project")
            assert tracer is not None
            assert tracer_provider is not None

            # Test creating a span
            with tracer.start_as_current_span("manager_integration_test") as span:
                span.set_attribute("integration.test", "manager_test")
                assert span is not None

        except Exception as e:
            pytest.fail(f"Failed to setup trace manager with real database: {e}")

    def test_error_handling_integration(self):
        """Test error handling with the actual ada_traces database."""
        if not settings.TRACES_DB_URL:
            pytest.skip("TRACES_DB_URL not configured")

        try:
            exporter = SQLSpanExporter()

            # Create a span that will cause an error (invalid JSON)
            bad_span = type(
                "BadSpan",
                (),
                {
                    "context": type("Context", (), {"span_id": "bad-span", "trace_id": "bad-trace"})(),
                    "name": "bad_span",
                    "status": type("Status", (), {"status_code": StatusCode.OK, "description": None})(),
                    "start_time": 1640995200000000000,
                    "end_time": 1640995201000000000,
                    "events": [],
                    "attributes": {},
                    "to_json": lambda: "invalid json",
                },
            )()

            # This should not crash the application
            result = exporter.export([bad_span])
            # Should still return SUCCESS even with bad span
            assert result.value == 0  # SUCCESS

            exporter.shutdown()

        except Exception as e:
            pytest.fail(f"Failed to handle errors with real database: {e}")

    def test_missing_timestamps_logging(self):
        """Test that missing timestamps are properly logged with warnings."""
        if not settings.TRACES_DB_URL:
            pytest.skip("TRACES_DB_URL not configured")

        import time

        try:
            # Capture log output
            log_stream = StringIO()
            log_handler = logging.StreamHandler(log_stream)
            log_handler.setLevel(logging.WARNING)

            # Get the logger used by the exporter
            exporter_logger = logging.getLogger("engine.trace.sql_exporter")
            original_level = exporter_logger.level
            exporter_logger.setLevel(logging.WARNING)
            exporter_logger.addHandler(log_handler)

            exporter = SQLSpanExporter()

            # Create a span with missing timestamps and unique ID
            unique_id = f"missing-time-span-{int(time.time())}"
            span_with_missing_timestamps = type(
                "SpanWithMissingTimestamps",
                (),
                {
                    "context": type("Context", (), {"span_id": unique_id, "trace_id": "missing-time-trace"})(),
                    "name": "span_with_missing_timestamps",
                    "status": type("Status", (), {"status_code": StatusCode.OK, "description": None})(),
                    "start_time": None,  # Missing start time
                    "end_time": None,  # Missing end time
                    "events": [],
                    "attributes": {"test.attribute": "test_value"},
                    "to_json": lambda self: json.dumps(
                        {
                            "context": {"span_id": unique_id, "trace_id": "missing-time-trace"},
                            "parent_id": None,
                            "attributes": {"test.attribute": "test_value"},
                        }
                    ),
                },
            )()

            # Export the span - this should trigger the warning log
            result = exporter.export([span_with_missing_timestamps])
            # The export should succeed with the unique ID
            assert result.value == 0, f"Export failed with result: {result}"

            exporter.shutdown()

            # Get the captured log output
            log_output = log_stream.getvalue()

            # Assert that the warning about missing timestamps was logged
            assert unique_id in log_output, "Span ID should be in log output"
            assert "start_time" in log_output or "end_time" in log_output, "Should mention missing timestamp(s)"
            assert "using fallback timestamp" in log_output, "Should mention fallback timestamp usage"

            # Clean up logging
            exporter_logger.removeHandler(log_handler)
            exporter_logger.setLevel(original_level)

        except Exception as e:
            pytest.fail(f"Failed to test missing timestamps logging: {e}")

    def test_partial_failure_logs_and_continues(self):
        """Test that exporter logs errors for bad spans but continues exporting good spans."""
        if not settings.TRACES_DB_URL:
            pytest.skip("TRACES_DB_URL not configured")

        import time
        from sqlalchemy import create_engine, text

        try:
            # Capture log output
            log_stream = StringIO()
            log_handler = logging.StreamHandler(log_stream)
            log_handler.setLevel(logging.ERROR)

            exporter_logger = logging.getLogger("engine.trace.sql_exporter")
            original_level = exporter_logger.level
            exporter_logger.setLevel(logging.ERROR)
            exporter_logger.addHandler(log_handler)

            exporter = SQLSpanExporter()

            # Good span (unique ID)
            good_id = f"good-span-{int(time.time())}"
            good_span = type(
                "GoodSpan",
                (),
                {
                    "context": type("Context", (), {"span_id": good_id, "trace_id": "good-trace"})(),
                    "name": "good_span",
                    "status": type("Status", (), {"status_code": StatusCode.OK, "description": None})(),
                    "start_time": 1640995200000000000,
                    "end_time": 1640995201000000000,
                    "events": [],
                    "attributes": {"test.attribute": "good_value"},
                    "to_json": lambda self: json.dumps(
                        {
                            "context": {"span_id": good_id, "trace_id": "good-trace"},
                            "parent_id": None,
                            "attributes": {"test.attribute": "good_value"},
                        }
                    ),
                },
            )()

            # Bad span (invalid to_json)
            bad_id = f"bad-span-{int(time.time())}"
            bad_span = type(
                "BadSpan",
                (),
                {
                    "context": type("Context", (), {"span_id": bad_id, "trace_id": "bad-trace"})(),
                    "name": "bad_span",
                    "status": type("Status", (), {"status_code": StatusCode.OK, "description": None})(),
                    "start_time": 1640995200000000000,
                    "end_time": 1640995201000000000,
                    "events": [],
                    "attributes": {"test.attribute": "bad_value"},
                    "to_json": lambda self: (_ for _ in ()).throw(Exception("JSON error for bad span")),
                },
            )()

            # Get initial count for good span
            engine = create_engine(settings.TRACES_DB_URL, echo=False)
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT COUNT(*) FROM spans WHERE span_id = :span_id"), {"span_id": good_id}
                )
                initial_count = result.scalar()

            # Export both spans in a batch
            result = exporter.export([bad_span, good_span])
            assert result.value == 0, f"Batch export should succeed for good spans: {result}"

            exporter.shutdown()

            # Check that the good span was exported
            with engine.connect() as conn:
                result = conn.execute(
                    text("SELECT COUNT(*) FROM spans WHERE span_id = :span_id"), {"span_id": good_id}
                )
                final_count = result.scalar()
                assert final_count > initial_count, "Good span should have been exported despite bad span in batch"

            # Check that the error for the bad span was logged
            log_output = log_stream.getvalue()
            assert bad_id in log_output, "Bad span ID should be in error log"
            assert "Error processing span" in log_output, "Should log error for bad span"
            assert "JSON error for bad span" in log_output, "Should log the specific error message"

            # Clean up logging
            exporter_logger.removeHandler(log_handler)
            exporter_logger.setLevel(original_level)

        except Exception as e:
            pytest.fail(f"Failed to test partial failure logging and continuation: {e}")


@pytest.mark.integration
def test_database_schema_verification():
    """Verify that the ada_traces database has the required tables."""
    if not settings.TRACES_DB_URL:
        pytest.skip("TRACES_DB_URL not configured")

    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(settings.TRACES_DB_URL, echo=False)
        with engine.connect() as conn:
            # Check for required tables in ada_traces
            tables = ["spans", "organization_usage", "alembic_version"]

            for table in tables:
                result = conn.execute(
                    text(
                        f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = '{table}'
                    );
                """
                    )
                )
                exists = result.scalar()
                assert exists, f"Required table '{table}' does not exist in ada_traces"

    except Exception as e:
        pytest.fail(f"Failed to verify ada_traces schema: {e}")


@pytest.mark.integration
def test_span_count_verification():
    """Verify that spans are being saved to the ada_traces database."""
    if not settings.TRACES_DB_URL:
        pytest.skip("TRACES_DB_URL not configured")

    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(settings.TRACES_DB_URL, echo=False)
        with engine.connect() as conn:
            # Get initial count
            result = conn.execute(text("SELECT COUNT(*) FROM spans"))
            initial_count = result.scalar()

            # Create and export a test span with proper attributes
            exporter = SQLSpanExporter()

            tracer_provider = TracerProvider()
            tracer = tracer_provider.get_tracer("count_test")

            with tracer.start_as_current_span("count_test_span") as span:
                # Set proper attributes that the exporter expects
                span.set_attribute("count.test", "true")
                span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, 10)
                span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, 5)
                span.set_attribute("organization_id", "test-org-count")

                # Export the span
                result = exporter.export([span])
                # Assert that export was successful
                assert result.value == 0, f"Export failed with result: {result}"

            exporter.shutdown()

            # Check that count increased
            result = conn.execute(text("SELECT COUNT(*) FROM spans"))
            final_count = result.scalar()

            # Check if there are any recent spans with our test attribute
            result = conn.execute(
                text(
                    """
                SELECT COUNT(*) FROM spans
                WHERE attributes LIKE '%count.test%'
                AND name = 'count_test_span'
            """
                )
            )
            test_span_count = result.scalar()

            # Assert that either the total count increased OR our specific test span was found
            assert (final_count > initial_count) or (test_span_count > 0), (
                f"Span export verification failed. "
                f"Initial count: {initial_count}, Final count: {final_count}, "
                f"Test span count: {test_span_count}"
            )

    except Exception as e:
        pytest.fail(f"Failed to verify span count in ada_traces: {e}")


@pytest.mark.integration
def test_organization_usage_table_schema():
    """Test that the organization_usage table has the correct schema."""
    if not settings.TRACES_DB_URL:
        pytest.skip("TRACES_DB_URL not configured")

    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(settings.TRACES_DB_URL, echo=False)
        with engine.connect() as conn:
            # Check the actual schema of organization_usage table
            result = conn.execute(
                text(
                    """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'organization_usage'
                ORDER BY ordinal_position
            """
                )
            )

            columns = result.fetchall()
            column_names = [col[0] for col in columns]

            # Verify expected columns exist
            expected_columns = ["id", "organization_id", "total_tokens"]
            for expected_col in expected_columns:
                assert expected_col in column_names, f"Expected column '{expected_col}' not found"

            # Test basic insert/select operations
            test_org_id = "test-org-schema"

            # Clean up any existing test data first
            conn.execute(
                text("DELETE FROM organization_usage WHERE organization_id = :org_id"), {"org_id": test_org_id}
            )

            # Insert test data (simple INSERT without ON CONFLICT since no unique constraint)
            conn.execute(
                text(
                    """
                INSERT INTO organization_usage (organization_id, total_tokens)
                VALUES (:org_id, :tokens)
            """
                ),
                {"org_id": test_org_id, "tokens": 100},
            )

            # Query the data back
            result = conn.execute(
                text(
                    """
                SELECT organization_id, total_tokens
                FROM organization_usage
                WHERE organization_id = :org_id
            """
                ),
                {"org_id": test_org_id},
            )

            row = result.first()
            assert row is not None, "Should find the inserted organization"
            assert row[0] == test_org_id
            assert row[1] == 100

            # Clean up
            conn.execute(
                text("DELETE FROM organization_usage WHERE organization_id = :org_id"), {"org_id": test_org_id}
            )

    except Exception as e:
        pytest.fail(f"Failed to test organization_usage table schema: {e}")
