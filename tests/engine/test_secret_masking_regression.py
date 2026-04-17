"""DRA-1225 regression surface: no over-redaction, no breakage.

Validates that the heuristic redaction layer (engine/log_redaction.py) and the
secret resolver simplification (secret_resolver.py always returns str) do not
break legitimate data flows.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from engine.components.tools.api_call_tool import APICallTool, APICallToolInputs, APICallToolOutputs
from engine.components.types import ComponentAttributes
from engine.log_redaction import REDACTED_PLACEHOLDER, redact_sensitive
from engine.secret_utils import unwrap_secret, unwrap_secrets
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

LEAK_MARKER = "LEAKED_IF_YOU_SEE_THIS_abc123"
ENDPOINT = "https://api.example.com/test"


# ---------------------------------------------------------------------------
# B1. redact_sensitive known false positives on benign fields
# ---------------------------------------------------------------------------


def test_b1_redact_sensitive_false_positives_on_token_usage():
    """token_usage, secret_count, cookie_policy are redacted due to heuristic substrings.

    These are KNOWN FALSE POSITIVES documented here. They do not block merge
    unless they break real functionality (e.g. LLM token counting in traces).
    The accepted behavior is REDACTED for these keys under the current
    SENSITIVE_FIELD_MARKERS heuristic.
    """
    payload = {
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
        "secret_count": 3,
        "cookie_policy": "strict",
        "model": "gpt-4",
    }

    redacted = redact_sensitive(payload)

    assert redacted["model"] == "gpt-4", "non-sensitive field must not be redacted"
    assert redacted["token_usage"] == REDACTED_PLACEHOLDER, "KNOWN FALSE POSITIVE: token_usage redacted (contains 'token')"
    assert redacted["secret_count"] == REDACTED_PLACEHOLDER, "KNOWN FALSE POSITIVE: secret_count redacted (contains 'secret')"
    assert redacted["cookie_policy"] == REDACTED_PLACEHOLDER, "KNOWN FALSE POSITIVE: cookie_policy redacted (contains 'cookie')"


# ---------------------------------------------------------------------------
# B2. serialize_to_json: normal payload preserved, sensitive redacted
# ---------------------------------------------------------------------------


def test_b2_serialize_to_json_preserves_normal_tool_call_payload():
    payload = {
        "query": "hello world",
        "limit": 10,
        "response": "here are your results",
    }

    result = serialize_to_json(payload)
    data = json.loads(result)

    assert data["query"] == "hello world"
    assert data["limit"] == 10
    assert data["response"] == "here are your results"


def test_b2_serialize_to_json_redacts_authorization_bearer():
    payload = {"authorization": f"Bearer {LEAK_MARKER}"}

    result = serialize_to_json(payload)

    assert LEAK_MARKER not in result
    assert REDACTED_PLACEHOLDER in result


def test_b2_serialize_to_json_bearer_token_in_free_text_is_redacted():
    """LLM output containing 'Bearer xxx' is redacted in the span via Bearer regex."""
    payload = {"output": f"Your token has been set. Bearer {LEAK_MARKER} is the value."}

    result = serialize_to_json(payload)

    assert LEAK_MARKER not in result
    assert f"Bearer {REDACTED_PLACEHOLDER}" in result


def test_b2_serialize_to_json_natural_word_token_not_redacted():
    """Free text mentioning 'token' without 'Bearer ' prefix passes through."""
    payload = {"output": "your token is ready"}

    result = serialize_to_json(payload)
    data = json.loads(result)

    assert data["output"] == "your token is ready"


# ---------------------------------------------------------------------------
# B3. api_call_tool error: non-sensitive detail preserved, sensitive redacted
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def api_tool(mock_trace_manager):
    return APICallTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="qa_api_tool"),
        method="GET",
        timeout=30,
    )


def test_b3_api_call_error_preserves_non_sensitive_response_body(api_tool):
    inputs = APICallToolInputs(endpoint=ENDPOINT, headers={}, fixed_parameters={})

    with patch.object(api_tool, "make_api_call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "status_code": 429,
            "error": "Too Many Requests",
            "response_body": {"error_code": 429, "retry_after": 60},
            "success": False,
        }

        result = asyncio.run(api_tool._run_without_io_trace(inputs))

    assert isinstance(result, APICallToolOutputs)
    assert result.success is False
    assert "retry_after" in result.output
    assert "error_code" in result.output
    assert LEAK_MARKER not in result.output


def test_b3_api_call_error_redacts_sensitive_key_in_response_body_but_preserves_rest(api_tool):
    inputs = APICallToolInputs(endpoint=ENDPOINT, headers={}, fixed_parameters={})

    with patch.object(api_tool, "make_api_call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "status_code": 500,
            "error": "Internal Server Error",
            "response_body": {"authorization": f"Bearer {LEAK_MARKER}", "detail": "bad request"},
            "success": False,
        }

        result = asyncio.run(api_tool._run_without_io_trace(inputs))

    assert result.success is False
    assert LEAK_MARKER not in result.output
    assert "[REDACTED]" in result.output
    assert "detail" in result.output
    assert "bad request" in result.output


# ---------------------------------------------------------------------------
# B4. secret_resolver: always returns str (not SecretStr)
# ---------------------------------------------------------------------------


def test_b4_replace_placeholders_full_match_returns_plain_str():
    from ada_backend.utils.secret_resolver import replace_secret_placeholders

    result = replace_secret_placeholders("@{ENV:TOKEN}", {"TOKEN": SecretStr("my-secret")})

    assert result == "my-secret"
    assert isinstance(result, str)
    assert not isinstance(result, SecretStr)


def test_b4_replace_placeholders_embedded_returns_plain_str():
    from ada_backend.utils.secret_resolver import replace_secret_placeholders

    result = replace_secret_placeholders("Bearer @{ENV:TOKEN}", {"TOKEN": SecretStr("my-secret")})

    assert result == "Bearer my-secret"
    assert isinstance(result, str)


def test_b4_str_result_is_usable_by_downstream_consumers():
    from ada_backend.utils.secret_resolver import replace_secret_placeholders

    result = replace_secret_placeholders(
        {"headers": {"Authorization": "Bearer @{ENV:API_KEY}"}},
        {"API_KEY": SecretStr("sk-12345")},
    )

    assert result["headers"]["Authorization"] == "Bearer sk-12345"
    assert isinstance(result["headers"]["Authorization"], str)
    assert not isinstance(result["headers"]["Authorization"], SecretStr)


# ---------------------------------------------------------------------------
# B5. unwrap_secrets bridges SecretStr → str before component receives params
# ---------------------------------------------------------------------------


def test_b5_unwrap_secrets_converts_secretstr_to_str_for_component_params():
    component_params = {
        "provider_api_key": SecretStr("sk-live-abc123"),
        "model": "gpt-4",
        "temperature": 0.7,
    }

    unwrapped = unwrap_secrets(component_params)

    assert unwrapped["provider_api_key"] == "sk-live-abc123"
    assert isinstance(unwrapped["provider_api_key"], str)
    assert not isinstance(unwrapped["provider_api_key"], SecretStr)
    assert unwrapped["model"] == "gpt-4"
    assert unwrapped["temperature"] == 0.7


# ---------------------------------------------------------------------------
# B6. resolve_oauth_access_token: SecretStr UUID does not crash (regression)
# ---------------------------------------------------------------------------


def test_b6_unwrap_secret_uuid_str_parses_correctly():
    """Regression: SecretStr wrapping a UUID string must unwrap to a valid UUID parseable str."""
    from uuid import UUID, uuid4

    connection_id = str(uuid4())
    secret = SecretStr(connection_id)

    raw = unwrap_secret(secret)

    assert raw == connection_id
    assert isinstance(raw, str)
    parsed = UUID(raw)
    assert str(parsed) == connection_id
