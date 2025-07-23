import json
import string
from typing import Union, Any
import logging

from fuzzywuzzy import fuzz, process


LOGGER = logging.getLogger(__name__)
BASE64_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
MAX_DISPLAY_CHARS = 10
MIN_LENGTH = 500


def _is_likely_base64(s: str) -> bool:
    """Lightning fast base64 detection using set operations."""
    length = len(s)

    # Quick length checks
    if length < MIN_LENGTH or length % 4 != 0:
        return False

    # Check for valid base64 characters (fast set lookup)
    # Handle padding separately
    content = s.rstrip("=")
    if not content or not all(c in BASE64_CHARS for c in content):
        return False

    # Check padding is only at the end (max 2 '=' chars)
    padding_count = length - len(content)
    return padding_count <= 2


def shorten_base64_string(obj: Any) -> Any:
    if isinstance(obj, str):
        # Check for data URL format first
        if obj.startswith("data:") and ";base64," in obj:
            prefix, base64_content = obj.split(";base64,", 1)
            if _is_likely_base64(base64_content) and len(base64_content) > MAX_DISPLAY_CHARS * 2:
                shortened_base64 = f"{base64_content[:MAX_DISPLAY_CHARS]}...{base64_content[-MAX_DISPLAY_CHARS:]}"
                return f"{prefix};base64,{shortened_base64}"
            return obj

        # Handle raw base64 strings
        elif _is_likely_base64(obj) and len(obj) > MAX_DISPLAY_CHARS * 2:
            return f"{obj[:MAX_DISPLAY_CHARS]}...{obj[-MAX_DISPLAY_CHARS:]}"

        return obj


def fuzzy_matching(query: str, list_of_entities: list[str], fuzzy_matching_candidates: int = 10):
    matching_entities = process.extract(
        query,
        list_of_entities,
        scorer=fuzz.partial_ratio,
        limit=fuzzy_matching_candidates,
    )
    return matching_entities


def format_qdrant_filter(filters: dict[str, Union[list[str], str]] | None, filtering_condition: str) -> dict:
    """Formats filtering criteria into a structured query format.

    Args:
        filters (dict[str, Union[list[str], str]] | None): A dictionary where keys are filter fields
            and values are either a single string or a list of strings.
        filtering_condition (str): The logical condition for filtering ("AND" or "OR").

    Returns:
        dict: A structured dictionary for filtering, following the "must" (AND) or "should" (OR) conditions.
    """
    LOGGER.info("Entering the filtering_formatting function")

    if not filters:
        return {}

    list_filters = [{"key": key, "match": {"any": value}} for key, value in filters.items()]

    if filtering_condition == "AND":
        return {"must": list_filters}
    if filtering_condition == "OR":
        return {"should": list_filters}
    return {}


def extract_vars_in_text_template(prompt_template: str) -> list[str]:
    return [fname for _, fname, _, _ in string.Formatter().parse(prompt_template) if fname]


def parse_openai_message_format(message: Union[str, list]) -> tuple[str, list[dict]]:
    if isinstance(message, str):
        return message, []

    text_content = ""
    files_content = []

    if isinstance(message, list):
        for item in message:
            if isinstance(item, dict):
                if "text" in item:
                    text_content += item["text"]
                if "file" in item:
                    files_content.append(
                        {
                            "type": "file",
                            "file": item["file"],
                        }
                    )

    return text_content, files_content


def load_str_to_json(str_to_parse: str) -> dict:
    try:
        parsed_string = json.loads(str_to_parse)
    except Exception as e:
        LOGGER.error(f"Failed to parse data: {str_to_parse} with error {e}")
        raise ValueError(f"Failed to parse data {str_to_parse}")
    return parsed_string
