from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SecretValue:
    _secret_value: str = field(repr=False)

    def get_secret_value(self) -> str:
        return self._secret_value

    def masked(self) -> str:
        return "***"

    def __str__(self) -> str:
        return self.masked()

    def __repr__(self) -> str:
        return "SecretValue('***')"

    def __bool__(self) -> bool:
        return bool(self._secret_value)

    def __len__(self) -> int:
        return len(self._secret_value)


def unwrap_secrets(value: Any) -> Any:
    if isinstance(value, SecretValue):
        return value.get_secret_value()
    if isinstance(value, dict):
        return {key: unwrap_secrets(inner_value) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [unwrap_secrets(inner_value) for inner_value in value]
    if isinstance(value, tuple):
        return tuple(unwrap_secrets(inner_value) for inner_value in value)
    if isinstance(value, set):
        return {unwrap_secrets(inner_value) for inner_value in value}
    return value
