import string
import logging
from typing import Optional

LOGGER = logging.getLogger(__name__)


def fill_prompt_template_with_priority(
    prompt_template: str,
    component_name: str = "",
    inputs_dict: Optional[dict] = None,
    ctx: Optional[dict] = None,
) -> str:
    """
    Fills the prompt template with variables from inputs_dict and ctx in priority order.
    Priority: inputs_dict -> ctx
    Ensures all values used can be converted to string.
    Raises ValueError for missing keys or uncastable values.

    Args:
        prompt_template: The template string with placeholders
        component_name: Name of the component for error messages
        inputs_dict: Dictionary from inputs/kwargs (function calling mode) - highest priority
        ctx: Dictionary from context (direct calls) - lower priority

    Returns:
        Filled template string
    """
    formatter = string.Formatter()
    prompt_keys = {field_name for _, field_name, _, _ in formatter.parse(prompt_template) if field_name}

    if not prompt_keys:
        return prompt_template

    # Build replacement dict with priority: inputs_dict -> ctx
    input_replacements = {}
    inputs_dict = inputs_dict or {}
    ctx = ctx or {}

    for prompt_var in prompt_keys:
        if prompt_var in inputs_dict:
            # Template var provided via inputs/kwargs (function calling mode) - highest priority
            input_replacements[prompt_var] = inputs_dict[prompt_var]
        elif prompt_var in ctx:
            # Template var provided via context (direct mode) - lower priority
            input_replacements[prompt_var] = ctx[prompt_var]
        else:
            # Missing required variable
            available_vars = list(set(inputs_dict.keys()) | set(ctx.keys()))
            error_message = (
                f"Missing template variable '{prompt_var}' needed in prompt template "
                f"of component '{component_name}'. "
                f"Available template vars: {available_vars}"
            )
            LOGGER.error(error_message)
            raise ValueError(error_message)

    # Convert all values to strings and format
    filtered_input = {}
    for key in prompt_keys:
        value = input_replacements[key]
        try:
            str_value = str(value)  # Try casting
        except Exception as e:
            LOGGER.error(f"Value for key '{key}' cannot be cast to string: {e}")
            raise ValueError(f"Value for key '{key}' cannot be cast to string: {e}")
        filtered_input[key] = str_value

    return prompt_template.format(**filtered_input)
