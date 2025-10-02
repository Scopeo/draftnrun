import json
import string
from typing import Union, Any
from typing import Callable, Optional, Tuple
from datetime import datetime
from pathlib import Path
import logging

from engine.temps_folder_utils import get_output_dir

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


def extract_vars_in_text_template(prompt_template: str) -> list[str]:
    return [fname for _, fname, _, _ in string.Formatter().parse(prompt_template) if fname]


def parse_openai_message_format(message: Union[str, list], provider: str) -> tuple[str, list[dict], list[dict]]:
    if isinstance(message, str):
        return message, [], []

    text_content = ""
    files_content = []
    images_content = []

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
                if "image_url" in item:
                    if provider == "openai":
                        images_content.append(
                            {
                                "type": "image_url",
                                "image_url": item["image_url"]["url"],
                            }
                        )
                    else:
                        images_content.append(
                            {
                                "type": "image_url",
                                "image_url": item["image_url"],
                            }
                        )

    return text_content, files_content, images_content


def load_str_to_json(str_to_parse: str) -> dict:
    try:
        parsed_string = json.loads(str_to_parse)
    except Exception as e:
        LOGGER.error(f"Failed to parse data: {str_to_parse} with error {e}")
        raise ValueError(f"Failed to parse data {str_to_parse}")
    return parsed_string


def prepare_markdown_output_path(
    markdown_content: str,
    filename: Optional[str] = None,
    output_dir_getter: Optional[Callable[[], Path]] = None,
    default_extension: str = ".docx",
) -> Tuple[str, Path, str]:
    """Prepare and validate markdown content and compute output path."""

    if not markdown_content:
        raise ValueError("No markdown content provided")

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"document_{timestamp}{default_extension}"
    else:
        # Ensure filename has an extension; if not, append default_extension
        p = Path(filename)
        if not p.suffix:
            filename = f"{filename}{default_extension}"

    # Resolve output directory
    if output_dir_getter is None:
        try:
            output_dir_getter = get_output_dir
        except Exception as e:
            raise RuntimeError("No output_dir_getter provided and failed to import get_output_dir") from e

    output_dir = output_dir_getter()
    output_path = output_dir / filename

    return markdown_content, output_path, filename
