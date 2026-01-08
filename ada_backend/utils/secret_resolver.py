import logging
import re
from typing import Any, Dict, Optional

from settings import settings

LOGGER = logging.getLogger(__name__)


_ENV_PATTERN = re.compile(r"@\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}")


def _resolve_single_placeholder(var_name: str, secret_mapping: Optional[Dict[str, str]]) -> str:
    """
    Resolve a single secret placeholder name to its value.

    Preference order:
    1. Organization-provided secret mapping
    2. Global settings attribute

    Logs resolution source without exposing variable names. Raises ValueError if not found.
    """
    if secret_mapping is not None and var_name in secret_mapping:
        LOGGER.debug("Secret resolved from organization configuration")
        return str(secret_mapping[var_name])

    env_val = getattr(settings, var_name, None)
    if env_val is not None:
        LOGGER.debug("Secret resolved from global settings")
        return str(env_val)

    # Only log variable name in debug mode, use generic message in production
    LOGGER.error("Secret placeholder resolution failed: variable not found in available sources")
    raise ValueError(
        f"Secret placeholder '@{{ENV:{var_name}}}' cannot be resolved: missing in organization secrets and settings",
    )


def _replace_in_string(text: str, secret_mapping: Optional[Dict[str, str]]) -> str:
    def _repl(match: re.Match) -> str:
        var_name = match.group(1)
        return _resolve_single_placeholder(var_name, secret_mapping)

    return _ENV_PATTERN.sub(_repl, text)


def replace_secret_placeholders(value: Any, secret_mapping: Optional[Dict[str, str]] = None) -> Any:
    """
    Recursively replace secret placeholders in strings within common Python containers.

    Supported placeholder format: @{ENV:KEY}

    - dict: processes keys and values if strings
    - list/tuple: processes items
    - str: replaces all occurrences within the string
    - other types are returned unchanged

    Raises ValueError if any placeholder cannot be resolved.
    """
    if isinstance(value, str):
        return _replace_in_string(value, secret_mapping)
    if isinstance(value, dict):
        return {
            (replace_secret_placeholders(k, secret_mapping) if isinstance(k, str) else k): replace_secret_placeholders(
                v, secret_mapping
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [replace_secret_placeholders(v, secret_mapping) for v in value]
    if isinstance(value, tuple):
        return tuple(replace_secret_placeholders(v, secret_mapping) for v in value)
    return value
