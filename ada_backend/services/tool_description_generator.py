"""Service for generating tool descriptions dynamically from port configurations."""

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.component_repository import (
    get_input_ports_for_component_version,
    get_tool_description,
    get_tool_description_component,
)
from ada_backend.repositories.port_configuration_repository import get_port_configurations
from ada_backend.schemas.pipeline.base import ToolDescriptionSchema

LOGGER = logging.getLogger(__name__)


class ToolProperties(BaseModel):
    """Tool properties for AI function calling."""

    tool_properties: dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema properties for tool parameters"
    )
    required_tool_properties: list[str] = Field(default_factory=list, description="List of required parameter names")


def generate_tool_description_from_ports(
    component_instance: db.ComponentInstance,
    tool_name: str | None = None,
    tool_description: str | None = None,
) -> ToolDescriptionSchema:
    """
    Generate tool description name and description for a component instance.

    Note: Tool properties for AI agents are built using get_tool_properties_from_ports()

    Args:
        component_instance: The component instance to generate tool description for
        tool_name: Optional tool name to use (defaults to generated name from instance)
        tool_description: Optional tool description (defaults to generated description)

    Returns:
        ToolDescriptionSchema with name and description
    """
    return ToolDescriptionSchema(
        name=tool_name or generate_tool_name(component_instance),
        description=tool_description or generate_tool_description(component_instance),
    )


def generate_tool_name(component_instance: db.ComponentInstance) -> str:
    """Generate a valid tool name from component instance (snake_case identifier)."""
    base_name = component_instance.ref or component_instance.name or f"tool_{component_instance.id}"
    sanitized = base_name.replace(" ", "_").replace("-", "_")
    sanitized = "".join(c if c.isalnum() or c == "_" else "" for c in sanitized)

    if sanitized and sanitized[0].isdigit():
        sanitized = f"tool_{sanitized}"

    return sanitized or "tool"


def generate_tool_description(component_instance: db.ComponentInstance) -> str:
    """Generate a descriptive text for the tool from component instance."""
    if component_instance.name:
        return f"Tool: {component_instance.name}"
    elif component_instance.ref:
        return f"Tool: {component_instance.ref}"
    else:
        return "A dynamically configured tool"


def get_tool_description_schema(
    session: Session,
    component_instance: db.ComponentInstance,
) -> ToolDescriptionSchema:
    db_tool_description = get_tool_description(session, component_instance.id)
    if not db_tool_description:
        db_tool_description = get_tool_description_component(session, component_instance.component_version_id)

    if db_tool_description:
        return ToolDescriptionSchema(
            id=db_tool_description.id,
            name=db_tool_description.name.replace(" ", "_"),
            description=db_tool_description.description,
        )

    return ToolDescriptionSchema(
        id=None,
        name=generate_tool_name(component_instance),
        description=generate_tool_description(component_instance),
    )


def get_tool_properties_from_ports(
    session: Session,
    component_instance: db.ComponentInstance,
) -> ToolProperties:
    port_configs = get_port_configurations(session, component_instance.id)

    if not port_configs:
        db_tool_description = get_tool_description(session, component_instance.id)
        if not db_tool_description:
            db_tool_description = get_tool_description_component(session, component_instance.component_version_id)

        if db_tool_description:
            return ToolProperties(
                tool_properties=db_tool_description.tool_properties or {},
                required_tool_properties=db_tool_description.required_tool_properties or [],
            )
        return ToolProperties()

    input_ports = get_input_ports_for_component_version(session, component_instance.component_version_id)
    port_def_map = {port.id: port for port in input_ports}

    tool_properties = {}
    required_tool_properties = []

    for config in port_configs:
        # Only ToolInputConfiguration has setup_mode
        if not isinstance(config, db.ToolInputConfiguration):
            continue
        if config.setup_mode != db.PortSetupMode.AI_FILLED:
            continue

        if config.port_definition_id is None:
            if config.custom_port_name:
                if config.json_schema_override:
                    tool_properties[config.custom_port_name] = config.json_schema_override
                else:
                    tool_properties[config.custom_port_name] = {
                        "type": _map_parameter_type(config.custom_parameter_type or "string"),
                        "description": config.custom_port_description or "",
                    }
                if config.is_required_override:
                    required_tool_properties.append(config.custom_port_name)
        else:
            port_def = port_def_map.get(config.port_definition_id)
            if not port_def:
                LOGGER.warning(f"Port definition not found for port configuration {config.id}")
                continue

            prop_description = config.ai_description_override or port_def.description

            if config.json_schema_override:
                tool_properties[port_def.name] = config.json_schema_override
            else:
                tool_properties[port_def.name] = {
                    "type": _map_parameter_type(port_def.parameter_type.value),
                    "description": prop_description or "",
                }

            is_required = not port_def.nullable or (config.is_required_override or False)
            if is_required:
                required_tool_properties.append(port_def.name)

    return ToolProperties(
        tool_properties=tool_properties,
        required_tool_properties=required_tool_properties,
    )


def _map_parameter_type(parameter_type: str) -> str:
    """Map ParameterType to JSON Schema type string."""
    type_mapping = {
        "string": "string",
        "integer": "integer",
        "float": "number",
        "boolean": "boolean",
        "json": "object",
    }
    return type_mapping.get(parameter_type, "string")
