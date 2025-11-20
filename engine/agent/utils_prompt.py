import logging
import re
import string

LOGGER = logging.getLogger(__name__)


def fill_prompt_template(prompt_template: str, component_name: str = "", variables: dict = None) -> str:
    """
    Fills the system prompt with only the keys required from variables.
    Ensures all values used can be converted to string.
    Raises ValueError for missing keys or uncastable values.

    Note: Single braces { and } that are not part of @{{}} field expressions are automatically
    escaped to prevent accidental template variable interpretation (e.g., {role} in text).
    """
    if not variables:
        return prompt_template

    # Escape single braces that are not part of @{{}} field expressions
    # This prevents accidental template variable interpretation while preserving field expressions
    # Pattern to match @{{...}} expressions - we'll preserve these
    field_expr_pattern = r"@\{\{[^}]+\}\}"
    # Find all field expressions and temporarily replace them with placeholders
    field_expressions = re.findall(field_expr_pattern, prompt_template)
    placeholder_map = {}
    escaped_template = prompt_template
    for i, expr in enumerate(field_expressions):
        placeholder = f"__FIELD_EXPR_{i}__"
        placeholder_map[placeholder] = expr
        escaped_template = escaped_template.replace(expr, placeholder, 1)

    # Escape single braces (not part of field expressions) by doubling them
    # This makes {role} become {{role}} which will render as {role} in the output
    escaped_template = escaped_template.replace("{", "{{").replace("}", "}}")

    # Restore original field expressions (they should remain as @{{...}}, not escaped)
    for placeholder, expr in placeholder_map.items():
        escaped_template = escaped_template.replace(placeholder, expr)

    formatter = string.Formatter()
    prompt_keys = {field_name for _, field_name, _, _ in formatter.parse(escaped_template) if field_name}

    missing_keys = prompt_keys - variables.keys()
    if missing_keys:
        error_message = (
            f"Missing template variable(s) {list(missing_keys)} needed in prompt template "
            f"of component '{component_name}'. "
            f"Available template vars: {list(variables.keys())}"
        )
        LOGGER.error(error_message)
        raise ValueError(error_message)

    filtered_input = {}
    for key in prompt_keys:
        value = variables[key]
        try:
            str_value = str(value)  # Try casting
        except Exception as e:
            LOGGER.error(f"Value for key '{key}' cannot be cast to string: {e}")
            raise ValueError(f"Value for key '{key}' cannot be cast to string: {e}")
        filtered_input[key] = str_value

    return escaped_template.format(**filtered_input)
