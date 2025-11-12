import string
import logging
from typing import Optional

LOGGER = logging.getLogger(__name__)


def fill_prompt_template(
    prompt_template: str,
    component_name: str = "",
    variables: Optional[dict[str, str]] = None,
) -> str:
    """
    Fills the prompt template with variables from the provided dictionary.
    Ensures all values used can be converted to string.
    Raises ValueError for missing keys or uncastable values.

    Args:
        prompt_template: The template string with placeholders
        component_name: Name of the component for error messages
        variables: Dictionary containing template variables to fill

    Returns:
        Filled template string
    """
    formatter = string.Formatter()
    prompt_keys = {field_name for _, field_name, _, _ in formatter.parse(prompt_template) if field_name}

    if not prompt_keys:
        return prompt_template

    variables = variables or {}

    missing_vars = prompt_keys - set(variables.keys())
    if missing_vars:
        available_vars = list(variables.keys())
        error_message = (
            f"Missing template variable(s) {list(missing_vars)} needed in prompt template "
            f"of component '{component_name}'. "
            f"Available template vars: {available_vars}"
        )
        LOGGER.error(error_message)
        raise ValueError(error_message)

    filtered_input = {}
    for key in prompt_keys:
        value = variables[key]
        try:
            str_value = str(value)
        except Exception as e:
            LOGGER.error(f"Value for key '{key}' cannot be cast to string: {e}")
            raise ValueError(f"Value for key '{key}' cannot be cast to string: {e}")
        filtered_input[key] = str_value

    return prompt_template.format(**filtered_input)
