import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ingestion_script.utils import METADATA_COLUMN_NAME


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    return value


def flatten_metadata_json(metadata_value):
    """Parse and flatten metadata JSON to a dictionary.

    Args:
        metadata_value: Can be a JSON string, dict, or None

    Returns:
        dict: Flattened metadata dictionary
    """
    if metadata_value is None:
        return {}

    if isinstance(metadata_value, str):
        try:
            parsed = json.loads(metadata_value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(metadata_value, dict):
        return metadata_value

    return {}


def prepare_rows_for_qdrant(rows: list[dict]) -> list[dict]:
    """Prepare rows for Qdrant by flattening metadata JSON column and ensuring JSON-safe values."""
    prepared_rows: list[dict] = []
    for row in rows:
        new_row = {k: _json_safe(v) for k, v in row.items()}
        if METADATA_COLUMN_NAME in new_row:
            flattened_metadata = flatten_metadata_json(new_row.pop(METADATA_COLUMN_NAME))
            for key, value in flattened_metadata.items():
                if key not in new_row:
                    new_row[key] = _json_safe(value)
        prepared_rows.append(new_row)
    return prepared_rows


def sanitize_for_json(value):
    """Sanitize a value for JSON encoding, handling invalid UTF-8 and already-encoded JSON strings."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            try:
                parsed = json.loads(value)
                return parsed
            except (json.JSONDecodeError, TypeError):
                return value.encode("utf-8", errors="replace").decode("utf-8")
        except Exception:
            return str(value).encode("utf-8", errors="replace").decode("utf-8")
    return value
