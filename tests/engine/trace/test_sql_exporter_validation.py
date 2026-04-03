import json
from unittest.mock import MagicMock, call, patch

import pytest
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import SpanContext, TraceFlags
from opentelemetry.trace.status import Status, StatusCode

from engine.trace.sql_exporter import SQLSpanExporter


def _make_valid_span(**overrides):
    span = MagicMock()
    span.context = SpanContext(
        trace_id=0x000000000000000000000000DEADBEEF,
        span_id=0x00000000DEADBEEF,
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    span.start_time = 1_000_000_000
    span.end_time = 2_000_000_000
    span.status = Status(StatusCode.OK)
    span.attributes = {"key": "value"}
    span.name = "test-span"
    span.events = []
    span.to_json.return_value = (
        '{"context": {"span_id": "00000000deadbeef", "trace_id": "000000000000000000000000deadbeef"}, '
        '"parent_id": null, '
        '"attributes": {"key": "value"}}'
    )
    for key, value in overrides.items():
        setattr(span, key, value)
    return span


def _parse_error(span):
    _, err = SQLSpanExporter._parse_span_or_error(span)
    return err


class TestParseSpanOrError:
    def test_valid_span_returns_dict(self):
        span = _make_valid_span()
        json_span, err = SQLSpanExporter._parse_span_or_error(span)
        assert err is None
        assert json_span is not None
        assert json_span["context"]["span_id"] == "00000000deadbeef"

    def test_missing_context(self):
        span = _make_valid_span(context=None)
        assert "context" in _parse_error(span)

    def test_zero_span_id(self):
        span = _make_valid_span(
            context=SpanContext(
                trace_id=0x000000000000000000000000DEADBEEF,
                span_id=0,
                is_remote=False,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
        )
        assert "context" in _parse_error(span)

    def test_zero_trace_id(self):
        span = _make_valid_span(
            context=SpanContext(
                trace_id=0,
                span_id=0x00000000DEADBEEF,
                is_remote=False,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
        )
        assert "context" in _parse_error(span)

    def test_missing_start_time(self):
        span = _make_valid_span(start_time=None)
        assert "start_time" in _parse_error(span)

    def test_missing_end_time(self):
        span = _make_valid_span(end_time=None)
        assert "end_time" in _parse_error(span)

    def test_missing_status(self):
        span = _make_valid_span(status=None)
        assert "status" in _parse_error(span)

    def test_missing_attributes(self):
        span = _make_valid_span(attributes=None)
        assert "attributes" in _parse_error(span)

    def test_json_serialization_failure(self):
        span = _make_valid_span()
        span.to_json.side_effect = TypeError("not serializable")
        assert "serialize" in _parse_error(span)

    def test_json_missing_context_keys(self):
        span = _make_valid_span()
        span.to_json.return_value = '{"context": {}, "attributes": {}}'
        assert "context" in _parse_error(span)


class TestExportWithSessionFiltersInvalidSpans:
    @pytest.fixture
    def exporter(self):
        return SQLSpanExporter()

    def test_all_invalid_returns_failure(self, exporter):
        bad_span = _make_valid_span(context=None)
        session = MagicMock()
        result = exporter._export_with_session(session, [bad_span])
        assert result == SpanExportResult.FAILURE
        session.commit.assert_not_called()

    def test_empty_batch_returns_success(self, exporter):
        session = MagicMock()
        result = exporter._export_with_session(session, [])
        assert result == SpanExportResult.SUCCESS

    @patch.object(SQLSpanExporter, "_export_span")
    def test_mixed_batch_exports_only_valid(self, mock_export_span, exporter):
        good = _make_valid_span(name="good")
        bad = _make_valid_span(context=None, name="bad")
        session = MagicMock()

        result = exporter._export_with_session(session, [good, bad])

        assert result == SpanExportResult.SUCCESS
        mock_export_span.assert_called_once_with(session, good, json.loads(good.to_json()))
        session.commit.assert_called_once()

    @patch.object(SQLSpanExporter, "_export_span")
    def test_all_valid_exports_all(self, mock_export_span, exporter):
        span1 = _make_valid_span(name="span1")
        span2 = _make_valid_span(name="span2")
        session = MagicMock()

        result = exporter._export_with_session(session, [span1, span2])

        assert result == SpanExportResult.SUCCESS
        assert mock_export_span.call_args_list == [
            call(session, span1, json.loads(span1.to_json())),
            call(session, span2, json.loads(span2.to_json())),
        ]
        session.commit.assert_called_once()
