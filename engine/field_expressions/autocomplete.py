# TODO: Refactor this to use a more robust parser instead of a regex. Also, it should share logic with the
# expression parser. Maybe a state machine would be better -> better defined states and transitions.
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FieldExpressionCursorContext:
    phase: Literal["instance", "port", "key"]
    instance_token: str
    port_token: str | None = None
    key_token: str | None = None


def get_cursor_context(expression_text: str, cursor_offset: int) -> FieldExpressionCursorContext | None:
    """Return the active reference context if the cursor is inside an @{{ }} block."""
    if expression_text is None:
        return None

    bounded_offset = max(0, min(cursor_offset, len(expression_text)))
    start = expression_text.rfind("@{{", 0, bounded_offset)
    if start == -1:
        return None

    # Ignore blocks already closed before the cursor.
    if expression_text.find("}}", start, bounded_offset) != -1:
        return None

    inner_before_cursor = expression_text[start + 3 : bounded_offset]
    stripped = inner_before_cursor.lstrip()

    # Empty or whitespace: still suggest instances.
    if stripped == "":
        return FieldExpressionCursorContext(phase="instance", instance_token="")

    dot_idx = stripped.find(".")
    colon_idx = stripped.find("::") if dot_idx != -1 else -1

    if dot_idx == -1:
        return FieldExpressionCursorContext(phase="instance", instance_token=_clean_token(stripped))

    instance_token = _clean_token(stripped[:dot_idx])
    port_slice = stripped[dot_idx + 1 :]

    if colon_idx == -1 or colon_idx < dot_idx:
        return FieldExpressionCursorContext(
            phase="port",
            instance_token=instance_token,
            port_token=_clean_token(port_slice),
        )

    port_token = _clean_token(stripped[dot_idx + 1 : colon_idx])
    key_token = _clean_token(stripped[colon_idx + 2 :])
    return FieldExpressionCursorContext(
        phase="key",
        instance_token=instance_token,
        port_token=port_token,
        key_token=key_token,
    )


def _clean_token(token: str) -> str:
    return token.strip()
