from pydantic import SecretStr

from engine.log_redaction import (
    REDACTED_PLACEHOLDER,
    is_sensitive_key,
    redact_sensitive,
    scrub_sentry_event,
)

LEAK_MARKER = "LEAKED_API_KEY_xyz789"


def test_is_sensitive_key_matches_common_markers():
    assert is_sensitive_key("api_key")
    assert is_sensitive_key("API_KEY")
    assert is_sensitive_key("x-api-key")
    assert is_sensitive_key("Authorization")
    assert is_sensitive_key("refresh_token")
    assert is_sensitive_key("client_secret")
    assert not is_sensitive_key("model")
    assert not is_sensitive_key("endpoint")
    assert not is_sensitive_key(None)


def test_redact_sensitive_redacts_values_by_key_name():
    payload = {
        "api_key": LEAK_MARKER,
        "nested": {"authorization": f"Bearer {LEAK_MARKER}", "keep": "public"},
        "list": [{"token": LEAK_MARKER}, {"model": "gpt-4"}],
        "public": "ok",
    }

    redacted = redact_sensitive(payload)

    assert redacted["api_key"] == REDACTED_PLACEHOLDER
    assert redacted["nested"]["authorization"] == REDACTED_PLACEHOLDER
    assert redacted["nested"]["keep"] == "public"
    assert redacted["list"][0]["token"] == REDACTED_PLACEHOLDER
    assert redacted["list"][1]["model"] == "gpt-4"
    assert LEAK_MARKER not in str(redacted)


def test_redact_sensitive_scrubs_bearer_token_in_plain_strings():
    message = f"GET /api failed with Authorization: Bearer {LEAK_MARKER} extra context"
    redacted = redact_sensitive(message)
    assert LEAK_MARKER not in redacted
    assert f"Bearer {REDACTED_PLACEHOLDER}" in redacted


def test_redact_sensitive_always_masks_secretstr():
    payload = {"model": "gpt-4", "token_like": SecretStr(LEAK_MARKER)}
    redacted = redact_sensitive(payload)
    assert redacted["token_like"] == REDACTED_PLACEHOLDER
    assert LEAK_MARKER not in str(redacted)


def test_scrub_sentry_event_redacts_nested_structures():
    event = {
        "message": f"boom: Bearer {LEAK_MARKER}",
        "extra": {"api_key": LEAK_MARKER, "public": 1},
        "exception": {"values": [{"value": f"token={LEAK_MARKER}"}]},
    }
    scrubbed = scrub_sentry_event(event)
    assert LEAK_MARKER not in str(scrubbed["message"])
    assert scrubbed["extra"]["api_key"] == REDACTED_PLACEHOLDER
    assert scrubbed["extra"]["public"] == 1
