from pydantic import SecretStr

from engine.secret_utils import unwrap_secrets
from engine.trace.serializer import serialize_to_json


def test_secret_str_masks_str_and_repr():
    secret = SecretStr("top-secret")

    assert str(secret) == "**********"
    assert repr(secret) == "SecretStr('**********')"
    assert secret.get_secret_value() == "top-secret"


def test_secret_str_truthiness_and_length():
    secret = SecretStr("abc123")

    assert bool(secret)
    assert len(secret) == 6


def test_unwrap_secrets_recursively():
    key_secret = SecretStr("masked-key")
    payload = {
        "token": SecretStr("abc"),
        "nested": [SecretStr("def"), {"inner": SecretStr("ghi")}],
        key_secret: "value",
    }

    result = unwrap_secrets(payload)
    assert result["token"] == "abc"
    assert result["nested"] == ["def", {"inner": "ghi"}]
    assert key_secret in result
    assert "masked-key" not in result


def test_serialize_to_json_masks_secret_values():
    payload = {
        "api_key": SecretStr("sk-12345"),
        "url": "https://example.com",
        "nested": [SecretStr("inner-secret"), "public"],
    }
    result = serialize_to_json(payload)
    assert "sk-12345" not in result
    assert "inner-secret" not in result
    assert "**********" in result
    assert "https://example.com" in result
    assert "public" in result
