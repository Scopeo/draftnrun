"""
Graph Runner Port Management Functions

Utilities for port type discovery used during field expression evaluation.
"""

import logging
from typing import Optional, Type

LOGGER = logging.getLogger(__name__)


def get_component_port_type(component, port_name: str, is_input: bool) -> Type | None:
    """Get port type from a component via its Pydantic I/O schema."""
    if not component:
        return None

    try:
        schema = component.get_inputs_schema() if is_input else component.get_outputs_schema()
        field_info = schema.model_fields.get(port_name)
        if field_info:
            return field_info.annotation
    except Exception as e:
        LOGGER.debug(f"Could not extract static type for {port_name}: {e}")

    return None


def get_target_field_type(component, port_name: str) -> Optional[type]:
    """Extract target field type from component's input schema."""
    try:
        schema = component.get_inputs_schema()
        field_info = schema.model_fields.get(port_name)
        if field_info:
            return field_info.annotation
    except Exception as e:
        LOGGER.warning(f"Could not extract field type for {port_name}: {e}")
    return str
