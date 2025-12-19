import json
from uuid import UUID

import pandas as pd

from ingestion_script.utils import METADATA_COLUMN_NAME, SOURCE_ID_COLUMN_NAME


def flatten_metadata_json(metadata_value):
    """Parse and flatten metadata JSON to a dictionary.

    Args:
        metadata_value: Can be a JSON string, dict, or None

    Returns:
        dict: Flattened metadata dictionary
    """
    if pd.isna(metadata_value) or metadata_value is None:
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


def prepare_df_for_qdrant(df):
    """Prepare DataFrame for Qdrant by flattening metadata JSON column.

    Reads metadata from JSONB column and flattens it into separate columns for Qdrant.
    """
    df = df.copy()
    if SOURCE_ID_COLUMN_NAME in df.columns:
        df[SOURCE_ID_COLUMN_NAME] = df[SOURCE_ID_COLUMN_NAME].apply(
            lambda value: str(value) if isinstance(value, UUID) else value
        )
    if METADATA_COLUMN_NAME in df.columns:

        def parse_and_flatten_metadata(row):
            """Parse metadata JSON and return flattened dict."""
            return flatten_metadata_json(row.get(METADATA_COLUMN_NAME))

        metadata_df = df.apply(parse_and_flatten_metadata, axis=1, result_type="expand")
        if not metadata_df.empty and len(metadata_df.columns) > 0:
            for col in metadata_df.columns:
                if col not in df.columns:
                    df[col] = metadata_df[col]

        df = df.drop(columns=[METADATA_COLUMN_NAME], errors="ignore")

    return df


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
