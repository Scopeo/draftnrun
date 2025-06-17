import json
import string
from typing import Union
import logging

from fuzzywuzzy import fuzz, process

LOGGER = logging.getLogger(__name__)


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


def convert_data_for_trace_manager_display(input_data, type_of_input):
    if isinstance(input_data, dict):
        trace_input = json.dumps(input_data)
        return trace_input
    elif isinstance(input_data, type_of_input):
        trace_input = input_data.last_message.content
        return trace_input
    else:
        LOGGER.error(f"Error with the {input_data} for trace display")
        raise ValueError(f"Error with the {input_data} for trace display")


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
