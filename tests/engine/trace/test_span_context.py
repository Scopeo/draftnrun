from unittest.mock import Mock, call, patch

import pytest

from engine.trace import span_context
from engine.trace.span_context import TracingSpanParams, get_tracing_span, set_tracing_span


@pytest.fixture(autouse=True)
def reset_tracing_context():
    """Ensure the tracing context is clean before and after each test."""
    from engine.trace.span_context import _tracing_context

    token = _tracing_context.set(None)
    yield
    _tracing_context.reset(token)


class TestSetTracingSpan:
    def test_creates_new_context_from_scratch(self):
        set_tracing_span(project_id="proj", organization_id="org", organization_llm_providers=["openai"])
        params = get_tracing_span()
        assert params is not None
        assert params.project_id == "proj"
        assert params.organization_id == "org"
        assert params.organization_llm_providers == ["openai"]

    def test_partial_set_before_full_set_merges(self):
        set_tracing_span(cron_id="cron-123")
        set_tracing_span(project_id="proj", organization_id="org", organization_llm_providers=["openai"])
        params = get_tracing_span()
        assert params is not None
        assert params.cron_id == "cron-123"
        assert params.project_id == "proj"

    def test_full_set_does_not_override_cron_id_when_not_provided(self):
        set_tracing_span(cron_id="cron-abc")
        set_tracing_span(
            project_id="proj",
            organization_id="org",
            organization_llm_providers=[],
            conversation_id="conv-1",
        )
        params = get_tracing_span()
        assert params.cron_id == "cron-abc"
        assert params.conversation_id == "conv-1"

    def test_merge_overwrites_only_provided_fields(self):
        set_tracing_span(project_id="old", organization_id="org", organization_llm_providers=[])
        set_tracing_span(project_id="new")
        params = get_tracing_span()
        assert params.project_id == "new"
        assert params.organization_id == "org"

    def test_unknown_field_raises_type_error(self):
        with pytest.raises(TypeError, match="Unknown tracing span fields"):
            set_tracing_span(nonexistent_field="value")

    def test_empty_call_creates_default_params(self):
        set_tracing_span()
        params = get_tracing_span()
        assert params is not None
        assert isinstance(params, TracingSpanParams)

    def test_set_tracing_span_syncs_tags_to_sentry(self):
        with patch("engine.trace.span_context.sentry_sdk.set_tag") as mock_set_tag:
            set_tracing_span(
                project_id="proj",
                organization_id="org",
                organization_llm_providers=["openai"],
                cron_id="cron-123",
            )

        mock_set_tag.assert_has_calls(
            [
                call("cron_id", "cron-123"),
                call("project_id", "proj"),
                call("organization_id", "org"),
            ],
            any_order=True,
        )

    def test_none_fields_not_sent_to_sentry(self):
        mock_scope = Mock()
        with (
            patch("engine.trace.span_context.sentry_sdk.get_isolation_scope", return_value=mock_scope),
            patch("engine.trace.span_context.sentry_sdk.set_tag") as mock_set_tag,
        ):
            set_tracing_span(project_id="proj", organization_id="org", organization_llm_providers=[], cron_id=None)

        assert all(args.args[0] != "cron_id" for args in mock_set_tag.call_args_list)
        mock_scope.remove_tag.assert_any_call("cron_id")

    def test_non_whitelisted_fields_not_sent(self):
        with patch("engine.trace.span_context.sentry_sdk.set_tag") as mock_set_tag:
            set_tracing_span(
                project_id="proj",
                organization_id="org",
                organization_llm_providers=["openai", "anthropic"],
                uuid_for_temp_folder="temp-123",
                conversation_id="conv-1",
            )

        sent_fields = {args.args[0] for args in mock_set_tag.call_args_list}
        assert "organization_llm_providers" not in sent_fields
        assert "shared_sandbox" not in sent_fields
        assert "uuid_for_temp_folder" not in sent_fields

    def test_sentry_tag_fields_extensibility(self, monkeypatch):
        monkeypatch.setattr(
            span_context,
            "SENTRY_TAG_FIELDS",
            (*span_context.SENTRY_TAG_FIELDS, "conversation_id"),
        )
        with patch("engine.trace.span_context.sentry_sdk.set_tag") as mock_set_tag:
            set_tracing_span(
                project_id="proj",
                organization_id="org",
                organization_llm_providers=[],
                conversation_id="conv-1",
            )

        assert ("conversation_id", "conv-1") in [args.args for args in mock_set_tag.call_args_list]
