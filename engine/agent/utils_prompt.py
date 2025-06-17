import string
import logging

LOGGER = logging.getLogger(__name__)


def fill_prompt_template_with_dictionary(input_dict: dict, prompt_template: str, component_name: str = "") -> str:
    """
    Fills the system prompt with only the keys required from input_dict.
    Ensures all values used can be converted to string.
    Raises ValueError for missing keys or uncastable values.
    """
    if not input_dict:
        return prompt_template

    formatter = string.Formatter()
    prompt_keys = {field_name for _, field_name, _, _ in formatter.parse(prompt_template) if field_name}

    missing_keys = prompt_keys - input_dict.keys()
    if missing_keys:
        error_message = (
            f"Missing keys needed in the prompt template :\n '{prompt_template[0:40]}' \n "
            f"of the component : '{component_name}' \n in input payload : "
            f"{input_dict}. \n Missing keys are : {missing_keys}"
        )
        LOGGER.error(error_message)
        raise ValueError(error_message)

    filtered_input = {}
    for key in prompt_keys:
        value = input_dict[key]
        try:
            str_value = str(value)  # Try casting
        except Exception as e:
            LOGGER.error(f"Value for key '{key}' cannot be cast to string: {e}")
            raise ValueError(f"Value for key '{key}' cannot be cast to string: {e}")
        filtered_input[key] = str_value

    return prompt_template.format(**filtered_input)
