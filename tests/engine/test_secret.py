from engine.secret import SecretValue, unwrap_secrets
from engine.trace.serializer import serialize_to_json


def test_secret_value_masks_str_and_repr():
    secret = SecretValue("top-secret")

    assert str(secret) == "***"
    assert repr(secret) == "SecretValue('***')"
    assert secret.get_secret_value() == "top-secret"
    assert secret.masked() == "***"


def test_secret_value_truthiness_and_length():
    secret = SecretValue("abc123")

    assert bool(secret)
    assert len(secret) == 6


def test_unwrap_secrets_recursively():
    key_secret = SecretValue("masked-key")
    payload = {
        "token": SecretValue("abc"),
        "nested": [SecretValue("def"), {"inner": SecretValue("ghi")}],
        key_secret: "value",
    }

    result = unwrap_secrets(payload)
    assert result["token"] == "abc"
    assert result["nested"] == ["def", {"inner": "ghi"}]
    assert key_secret in result
    assert "masked-key" not in result


def test_serialize_to_json_masks_secret_values():
    payload = {
        "api_key": SecretValue("sk-12345"),
        "url": "https://example.com",
        "nested": [SecretValue("inner-secret"), "public"],
    }
    result = serialize_to_json(payload)
    assert "sk-12345" not in result
    assert "inner-secret" not in result
    assert "***" in result
    assert "https://example.com" in result
    assert "public" in result
