import json
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.output_port_instance_repository import (
    create_output_port_instance,
    delete_output_port_instances_for_component_instance,
)
from ada_backend.repositories.port_mapping_repository import is_drives_output_schema_port

LOGGER = logging.getLogger(__name__)


def extract_schema_keys(value) -> list[str]:
    """Extract top-level keys from an output schema value.

    The output_format field uses a flat dict where keys are the port names directly,
    e.g. {"name": "string", "age": "number"} → ["name", "age"].
    """
    if isinstance(value, str):
        try:
            schema = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []
    elif isinstance(value, dict):
        schema = value
    else:
        return []

    if not isinstance(schema, dict):
        return []

    return list(schema.keys())


def sync_output_port_instances_from_schema(
    session: Session,
    component_instance_id: UUID,
    component_version_id: UUID,
    field_name: str,
    value,
) -> None:
    """Create OutputPortInstance rows for each top-level key of the output schema value."""
    if not is_drives_output_schema_port(session, component_version_id, field_name):
        return

    keys = extract_schema_keys(value)

    delete_output_port_instances_for_component_instance(session, component_instance_id)

    if not keys:
        LOGGER.debug(
            f"Cleared OutputPortInstance(s) for drives_output_schema field '{field_name}' "
            f"on instance {component_instance_id} (empty or unparseable value)"
        )
        return

    for key in keys:
        create_output_port_instance(
            session=session,
            component_instance_id=component_instance_id,
            name=key,
        )
    LOGGER.info(
        f"Synced {len(keys)} OutputPortInstance(s) for instance {component_instance_id} "
        f"from field '{field_name}': {keys}"
    )
