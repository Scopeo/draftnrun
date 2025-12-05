import logging
import re

from engine.agent.errors import (
    KeyTypePromptTemplateError,
    MissingKeyPromptTemplateError,
)

LOGGER = logging.getLogger(__name__)


def fill_prompt_template(prompt_template: str, component_name: str = "", variables: dict = None) -> str:
    """
    Fills the system prompt with only the keys required from variables.
    Ensures all values used can be converted to string.
    Raises MissingKeyPromptTemplateError for missing keys or
    KeyTypePromptTemplateError for uncastable string values.

    Note: Only double braces {{variable}} are supported for template variables.
    Field expressions use @{{expression}} format. Single braces { and } that are not
    part of these patterns are automatically escaped to prevent accidental template variable interpretation.
    """
    if variables is None:
        return prompt_template

    field_expr_pattern = r"@\{\{[^}]+\}\}"
    field_expressions = re.findall(field_expr_pattern, prompt_template)
    placeholder_map = {}
    escaped_template = prompt_template
    for i, expr in enumerate(field_expressions):
        placeholder = f"__FIELD_EXPR_{i}__"
        placeholder_map[placeholder] = expr
        escaped_template = escaped_template.replace(expr, placeholder, 1)

    # Only detect double braces {{variable}}
    double_brace_pattern = r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}"
    template_vars = set()
    all_detected_vars = set()
    for match in re.finditer(double_brace_pattern, escaped_template):
        var_name = match.group(1)
        all_detected_vars.add(var_name)
        if var_name in variables:
            template_vars.add(var_name)

    missing_keys = all_detected_vars - variables.keys()
    if missing_keys:
        LOGGER.error(
            f"Missing template variable(s) {list(missing_keys)} needed in prompt template "
            f"of component '{component_name}'. "
            f"Available template vars: {list(variables.keys())}"
        )
        raise MissingKeyPromptTemplateError(missing_keys=list(missing_keys))

    for var_name in template_vars:
        if var_name in variables:
            double_brace = "{{" + var_name + "}}"
            placeholder = f"__TEMPLATE_VAR_{var_name}__"
            escaped_template = escaped_template.replace(double_brace, placeholder)
            placeholder_map[placeholder] = "{" + var_name + "}"

    escaped_template = escaped_template.replace("{", "{{").replace("}", "}}")

    for placeholder, original in placeholder_map.items():
        escaped_template = escaped_template.replace(placeholder, original)

    filtered_input = {}
    for key in template_vars:
        value = variables[key]
        try:
            str_value = str(value)
        except Exception as e:
            LOGGER.error(
                f"Value for key '{key}' cannot be cast to string in prompt template "
                f"of component '{component_name}': {e}"
            )
            raise KeyTypePromptTemplateError(key=key, error=e)
        filtered_input[key] = str_value

    return escaped_template.format(**filtered_input)
