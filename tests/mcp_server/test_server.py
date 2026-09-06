"""Tests for the Sentry scrubbers — security-critical redaction logic."""

from mcp_server.server import _before_send, _scrub_sentry_value


def test_scrubs_bearer_tokens_in_strings():
    value = "Request failed: Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig"
    assert "eyJhbGciOiJIUzI1NiJ9" not in _scrub_sentry_value(value)
    assert "Bearer [REDACTED]" in _scrub_sentry_value(value)


def test_scrubs_sensitive_keys_case_insensitively():
    event = {
        "Authorization": "Bearer abc",
        "api_key": "sk-123",
        "PASSWORD": "hunter2",
        "X-Cookie": "session=42",
        "jwt_token": "ey...",
        "safe_field": "keep me",
    }
    scrubbed = _scrub_sentry_value(event)
    assert scrubbed["Authorization"] == "[REDACTED]"
    assert scrubbed["api_key"] == "[REDACTED]"
    assert scrubbed["PASSWORD"] == "[REDACTED]"
    assert scrubbed["X-Cookie"] == "[REDACTED]"
    assert scrubbed["jwt_token"] == "[REDACTED]"
    assert scrubbed["safe_field"] == "keep me"


def test_scrubs_user_id_fields_including_x_prefixed():
    event = {"user": {"id": "u-1"}, "user_id": "u-1", "x_user_id": "u-1", "username": "keep"}
    scrubbed = _scrub_sentry_value(event)
    assert scrubbed["user"] == "[REDACTED]"
    assert scrubbed["user_id"] == "[REDACTED]"
    assert scrubbed["x_user_id"] == "[REDACTED]"
    assert scrubbed["username"] == "keep"


def test_scrubs_nested_structures():
    event = {
        "request": {
            "headers": {"authorization": "Bearer abc"},
            "breadcrumbs": [{"message": "sent Bearer xyz to backend"}],
        }
    }
    scrubbed = _scrub_sentry_value(event)
    assert scrubbed["request"]["headers"]["authorization"] == "[REDACTED]"
    assert "xyz" not in scrubbed["request"]["breadcrumbs"][0]["message"]


def test_before_send_returns_scrubbed_event():
    event = {"extra": {"token": "secret-token", "detail": "Bearer abc123"}}
    result = _before_send(event, {})
    assert result["extra"]["token"] == "[REDACTED]"
    assert "abc123" not in result["extra"]["detail"]


def test_non_sensitive_scalars_pass_through():
    assert _scrub_sentry_value(42) == 42
    assert _scrub_sentry_value(None) is None
    assert _scrub_sentry_value("plain message") == "plain message"
