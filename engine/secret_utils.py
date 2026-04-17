from typing import Any

from pydantic import SecretStr


def unwrap_secret(value: SecretStr | str | None) -> str | None:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


def unwrap_secrets(value: Any) -> Any:
    value = unwrap_secret(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return {key: unwrap_secrets(inner_value) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [unwrap_secrets(inner_value) for inner_value in value]
    if isinstance(value, tuple):
        return tuple(unwrap_secrets(inner_value) for inner_value in value)
    if isinstance(value, set):
        return {unwrap_secrets(inner_value) for inner_value in value}
    return value
