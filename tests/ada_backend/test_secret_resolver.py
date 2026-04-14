import pytest

from ada_backend.utils.secret_resolver import replace_secret_placeholders
from engine.secret import SecretValue


def test_replace_secret_placeholders_unwraps_secret_value_from_mapping():
    payload = {"headers": {"Authorization": "Bearer @{ENV:API_TOKEN}"}}
    result = replace_secret_placeholders(payload, {"API_TOKEN": SecretValue("secret-token")})
    assert result == {"headers": {"Authorization": "Bearer secret-token"}}


def test_replace_secret_placeholders_handles_nested_structures():
    payload = ["@{ENV:API_TOKEN}", {"token": "@{ENV:API_TOKEN}"}]
    result = replace_secret_placeholders(payload, {"API_TOKEN": SecretValue("secret-token")})
    assert result == ["secret-token", {"token": "secret-token"}]


def test_replace_secret_placeholders_raises_for_unknown_secret():
    with pytest.raises(ValueError, match="cannot be resolved"):
        replace_secret_placeholders("Bearer @{ENV:UNKNOWN_SECRET}", {})
