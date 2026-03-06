import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.graph_runner_repository import get_start_components
from ada_backend.repositories.input_port_instance_repository import get_input_port_instances_for_component_instance
from ada_backend.schemas.pipeline.graph_schema import PlaygroundFieldType

LOGGER = logging.getLogger(__name__)

START_PAYLOAD_SCHEMA_PORT_NAME = "payload_schema"


def get_nesting_depth(obj, current_depth=0):
    """Calculate the maximum nesting depth of a dict or list."""
    if not isinstance(obj, (dict, list)):
        return current_depth

    if isinstance(obj, dict):
        if not obj:
            return current_depth
        return max(get_nesting_depth(v, current_depth + 1) for v in obj.values())

    if isinstance(obj, list):
        if not obj:
            return current_depth
        return max(get_nesting_depth(item, current_depth + 1) for item in obj)

    return current_depth


def classify_playground_field(key, value) -> PlaygroundFieldType:
    if key == "messages":
        return PlaygroundFieldType.MESSAGES

    # Detect OpenAI file format: {"type": "file", "file": {...}}
    if isinstance(value, dict) and value.get("type") == "file" and "file" in value:
        return PlaygroundFieldType.FILE

    depth = get_nesting_depth(value)
    if depth > 2:
        return PlaygroundFieldType.JSON
    return PlaygroundFieldType.SIMPLE


def extract_payload_schema_from_instance(session: Session, component_instance_id: UUID) -> Optional[dict]:
    port_instances = get_input_port_instances_for_component_instance(
        session, component_instance_id, eager_load_field_expression=True
    )
    for port_instance in port_instances:
        if port_instance.name == START_PAYLOAD_SCHEMA_PORT_NAME and port_instance.field_expression:
            expr = port_instance.field_expression.expression_json
            if expr.get("type") == "literal":
                try:
                    return json.loads(expr["value"])
                except (json.JSONDecodeError, KeyError):
                    LOGGER.warning(f"Failed to parse payload_schema for instance {component_instance_id}")
    return None


def classify_schema_fields(playground_input_schema: dict) -> dict[str, PlaygroundFieldType]:
    """Classify each field in the playground schema by type."""
    return {key: classify_playground_field(key, value) for key, value in playground_input_schema.items()}


def extract_playground_configuration(
    session: Session, graph_runner_id: UUID
) -> tuple[Optional[dict], Optional[dict[str, PlaygroundFieldType]]]:
    start_components = get_start_components(session, graph_runner_id)
    if not start_components:
        return None, None

    start_node = start_components[0]
    playground_input_schema = extract_payload_schema_from_instance(session, start_node.id)
    playground_field_types = None
    if playground_input_schema:
        playground_field_types = classify_schema_fields(playground_input_schema)

    return playground_input_schema, playground_field_types
