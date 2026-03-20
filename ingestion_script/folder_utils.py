import json
from uuid import UUID

from ingestion_script.utils import METADATA_COLUMN_NAME, SOURCE_ID_COLUMN_NAME


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
    """Prepare rows for Qdrant by flattening metadata JSON column."""
    prepared_rows: list[dict] = []
    for row in rows:
        new_row = dict(row)
        if SOURCE_ID_COLUMN_NAME in new_row:
            source_id_value = new_row[SOURCE_ID_COLUMN_NAME]
            if isinstance(source_id_value, UUID):
                new_row[SOURCE_ID_COLUMN_NAME] = str(source_id_value)
        if METADATA_COLUMN_NAME in new_row:
            flattened_metadata = flatten_metadata_json(new_row.pop(METADATA_COLUMN_NAME))
            for key, value in flattened_metadata.items():
                if key not in new_row:
                    new_row[key] = value
        prepared_rows.append(new_row)
    return prepared_rows


def prepare_df_for_qdrant(df):
    """Legacy wrapper that accepts a pandas DataFrame."""
    rows = df.to_dict(orient="records")
    import pandas as pd
    return pd.DataFrame(prepare_rows_for_qdrant(rows))


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
