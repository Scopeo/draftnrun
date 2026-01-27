import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.seed.seed_start import START_PAYLOAD_PARAMETER_NAME
from ada_backend.repositories.graph_runner_repository import get_start_components
from ada_backend.schemas.pipeline.graph_schema import PlaygroundFieldType
from ada_backend.services.pipeline.get_pipeline_service import get_component_instance

LOGGER = logging.getLogger(__name__)


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


def extract_playground_schema_from_component(component_instance) -> Optional[dict]:
    for param in component_instance.parameters:
        if param.name == START_PAYLOAD_PARAMETER_NAME:
            try:
                if param.value and isinstance(param.value, dict):
                    return param.value
                elif param.value and isinstance(param.value, str):
                    return json.loads(param.value)
            except json.JSONDecodeError:
                LOGGER.warning(
                    f"Failed to parse payload_schema for component {component_instance.id}. "
                    f"Invalid JSON in parameter value."
                )
            except Exception as e:
                LOGGER.warning(f"Unexpected error parsing payload_schema for component {component_instance.id}: {e}")
            break
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
    component_instance = get_component_instance(
        session,
        start_node.id,
        is_start_node=True,
    )

    playground_input_schema = extract_playground_schema_from_component(component_instance)
    playground_field_types = None
    if playground_input_schema:
        playground_field_types = classify_schema_fields(playground_input_schema)

    return playground_input_schema, playground_field_types
