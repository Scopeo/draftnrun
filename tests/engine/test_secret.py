from engine.secret import SecretValue, unwrap_secrets


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
    payload = {
        "token": SecretValue("abc"),
        "nested": [SecretValue("def"), {"inner": SecretValue("ghi")}],
        SecretValue("masked-key"): "value",
    }

    assert unwrap_secrets(payload) == {
        "token": "abc",
        "nested": ["def", {"inner": "ghi"}],
        "masked-key": "value",
    }
