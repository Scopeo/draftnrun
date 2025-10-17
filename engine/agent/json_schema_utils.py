"""Utility functions for working with JSON Schema."""

import json
import logging
from typing import Any

from jsonschema import Draft7Validator, ValidationError

LOGGER = logging.getLogger(__name__)


def extract_defaults_from_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Extract default values from a JSON Schema.

    This function recursively traverses a JSON Schema and builds a dictionary
    of default values based on the 'default' keywords found in the schema.

    Args:
        schema: A JSON Schema dictionary (draft-07 compatible)

    Returns:
        A dictionary containing the default values extracted from the schema
    """
    if not isinstance(schema, dict):
        return {}

    # Check if there's a top-level default
    if "default" in schema:
        return schema["default"]

    result = {}

    # Handle object type schemas
    if schema.get("type") == "object" and "properties" in schema:
        for prop_name, prop_schema in schema["properties"].items():
            if "default" in prop_schema:
                result[prop_name] = prop_schema["default"]
            elif prop_schema.get("type") == "object":
                # Recursively extract defaults from nested objects
                nested_defaults = extract_defaults_from_schema(prop_schema)
                if nested_defaults:
                    result[prop_name] = nested_defaults
            elif prop_schema.get("type") == "array" and "default" in prop_schema:
                result[prop_name] = prop_schema["default"]

    return result


def validate_and_apply_defaults(data: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """
    Validate data against a JSON Schema and apply default values.

    This function validates the input data against the provided schema,
    and fills in missing fields with their default values from the schema.

    Args:
        data: Input data to validate and apply defaults to
        schema: JSON Schema to validate against and extract defaults from

    Returns:
        The input data with defaults applied for missing fields

    Raises:
        ValidationError: If the data doesn't conform to the schema
    """
    # Extract defaults from schema
    defaults = extract_defaults_from_schema(schema)

    # Create a copy of the input data
    result = data.copy()

    # Apply defaults for missing fields
    for key, default_value in defaults.items():
        if key not in result:
            result[key] = default_value

    # Validate the result against the schema
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(result))

    if errors:
        # Log validation errors
        for error in errors:
            LOGGER.error(f"Schema validation error: {error.message} at path {list(error.path)}")

        # Raise the first error
        raise errors[0]

    return result


def parse_json_schema_string(schema_string: str) -> dict[str, Any]:
    """
    Parse a JSON Schema string and validate it's a valid schema.

    Args:
        schema_string: JSON Schema as a string

    Returns:
        Parsed JSON Schema as a dictionary

    Raises:
        json.JSONDecodeError: If the string is not valid JSON
        ValidationError: If the JSON is not a valid JSON Schema
    """
    try:
        schema = json.loads(schema_string)
    except json.JSONDecodeError as e:
        LOGGER.error(f"Invalid JSON in schema string: {e}")
        raise

    # Basic validation that it looks like a schema
    if not isinstance(schema, dict):
        raise ValueError("Schema must be a JSON object")

    # Validate the schema itself
    try:
        Draft7Validator.check_schema(schema)
    except Exception as e:
        LOGGER.error(f"Invalid JSON Schema: {e}")
        raise ValidationError(f"Invalid JSON Schema: {e}")

    return schema
