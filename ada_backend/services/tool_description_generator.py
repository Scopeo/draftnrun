"""Dynamically generate ToolDescription from port configurations.

Builds ToolDescription objects on-the-fly by inspecting each
input port's ToolPortConfiguration (or falling back to PortDefinition defaults).

Tool-level name comes from ComponentInstance.name (or Component.name).
Tool-level description comes from ComponentInstance.tool_description_override
(or ComponentVersion.description).
"""

import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ComponentInstance,
    JsonSchemaType,
    ParameterType,
    PortSetupMode,
    PortType,
)
from ada_backend.repositories.tool_port_configuration_repository import (
    get_tool_port_configurations,
)
from engine.components.types import ToolDescription

LOGGER = logging.getLogger(__name__)

_TOOL_NAME_MAX_LENGTH = 64


def sanitize_tool_name(raw_name: str) -> str:
    """Sanitize a raw name into a valid LLM function-calling tool name.

    Keeps only alphanumeric characters, underscores, and hyphens.
    Matches the common constraint ``^[a-zA-Z0-9_-]{1,64}$`` used by
    OpenAI / Anthropic function-calling APIs.
    """
    name = raw_name.strip()
    name = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_-")
    return name[:_TOOL_NAME_MAX_LENGTH] or "unnamed_tool"


PARAMETER_TYPE_TO_JSON_SCHEMA: dict[str, dict[str, str]] = {
    ParameterType.STRING: {"type": "string"},
    ParameterType.INTEGER: {"type": "integer"},
    ParameterType.FLOAT: {"type": "number"},
    ParameterType.BOOLEAN: {"type": "boolean"},
    ParameterType.JSON: {"type": "object"},
    ParameterType.ARRAY: {"type": "array", "items": {"type": "string"}},
}

JSON_SCHEMA_TYPE_MAP: dict[str, dict[str, str]] = {
    JsonSchemaType.STRING: {"type": "string"},
    JsonSchemaType.INTEGER: {"type": "integer"},
    JsonSchemaType.NUMBER: {"type": "number"},
    JsonSchemaType.BOOLEAN: {"type": "boolean"},
    JsonSchemaType.OBJECT: {"type": "object"},
    JsonSchemaType.ARRAY: {"type": "array"},
}


def _resolve_tool_name_and_description(
    session: Session,
    component_instance: ComponentInstance,
) -> tuple[Optional[str], Optional[str]]:
    """Derive tool name and description without the ToolDescription table.

    - name: ComponentInstance.name -> Component.name
    - description: ComponentInstance.tool_description_override -> ComponentVersion.description
    """
    component_version = component_instance.component_version
    component = component_version.component if component_version else None

    tool_name = component_instance.name
    if not tool_name and component:
        tool_name = component.name

    tool_description = component_instance.tool_description_override
    if not tool_description and component_version:
        tool_description = component_version.description

    return tool_name, tool_description


def _get_tool_eligible_port_definitions(
    session: Session,
    component_version_id,
) -> list[db.PortDefinition]:
    """Return input PortDefinitions where is_tool_input=True."""
    return (
        session.query(db.PortDefinition)
        .filter(
            db.PortDefinition.component_version_id == component_version_id,
            db.PortDefinition.port_type == PortType.INPUT,
            db.PortDefinition.is_tool_input.is_(True),
        )
        .all()
    )


def _build_property_schema(
    port_def: Optional[db.PortDefinition],
    config: Optional[db.ToolPortConfiguration],
) -> dict[str, Any]:
    """Build the JSON Schema property dict for a single AI_FILLED port.

    Priority order:
    1. json_schema_override on config (full replacement, per-instance)
    2. default_tool_json_schema on PortDefinition (full replacement, per-component)
    3. Attribute overrides on config (ai_name_override, ai_description_override, ...)
    4. PortDefinition parameter_type + description fallback
    """
    if config and config.json_schema_override:
        schema = dict(config.json_schema_override)
        if config.ai_description_override and "description" not in schema:
            schema["description"] = config.ai_description_override
        return schema

    if port_def and isinstance(port_def.default_tool_json_schema, dict):
        return dict(port_def.default_tool_json_schema)

    schema: dict[str, Any] = {}

    if config and config.custom_parameter_type:
        schema.update(JSON_SCHEMA_TYPE_MAP.get(config.custom_parameter_type, {"type": "string"}))
    elif port_def:
        schema.update(PARAMETER_TYPE_TO_JSON_SCHEMA.get(port_def.parameter_type, {"type": "string"}))
    else:
        schema["type"] = "string"

    if config and config.ai_description_override:
        schema["description"] = config.ai_description_override
    elif port_def and port_def.description:
        schema["description"] = port_def.description

    return schema


def _is_port_required(
    port_def: Optional[db.PortDefinition],
    config: Optional[db.ToolPortConfiguration],
) -> bool:
    """Determine if a port should be marked as required."""
    if config and config.is_required_override is not None:
        return config.is_required_override
    if port_def:
        return not port_def.nullable
    return True


def _resolve_property_name(
    port_def: Optional[db.PortDefinition],
    config: Optional[db.ToolPortConfiguration],
) -> Optional[str]:
    """Resolve the property name for a tool port from config overrides or definition."""
    if config and config.ai_name_override:
        return config.ai_name_override
    if port_def:
        return port_def.name
    if config:
        return config.input_port_instance.name if config.input_port_instance else None
    return None


def generate_tool_description(
    session: Session,
    component_instance: ComponentInstance,
) -> Optional[ToolDescription]:
    """Build a ToolDescription dynamically from port configurations.

    Tool name and description are derived from the component instance / version.
    Tool properties are computed from PortDefinitions + ToolPortConfigurations.
    """
    tool_name, tool_description = _resolve_tool_name_and_description(session, component_instance)
    if not tool_name:
        LOGGER.warning(f"No tool name resolvable for component instance {component_instance.id}.")
        return None

    tool_name = sanitize_tool_name(tool_name)

    port_defs = _get_tool_eligible_port_definitions(session, component_instance.component_version_id)

    configs = get_tool_port_configurations(session, component_instance.id, eager_load_port_definition=True)
    config_by_port_def_id: dict = {c.port_definition_id: c for c in configs if c.port_definition_id}
    custom_configs = [c for c in configs if c.port_definition_id is None]

    port_config_pairs: list[tuple[Optional[db.PortDefinition], Optional[db.ToolPortConfiguration]]] = [
        (port_def, config_by_port_def_id.get(port_def.id)) for port_def in port_defs
    ] + [(None, config) for config in custom_configs]

    tool_properties: dict[str, dict[str, Any]] = {}
    required_properties: list[str] = []

    for port_def, config in port_config_pairs:
        effective_mode = config.setup_mode if config else PortSetupMode.AI_FILLED
        if effective_mode != PortSetupMode.AI_FILLED:
            continue

        property_name = _resolve_property_name(port_def, config)
        if not property_name:
            LOGGER.warning(f"Custom port config {config.id} has no name, skipping.")
            continue

        tool_properties[property_name] = _build_property_schema(port_def, config)

        if _is_port_required(port_def, config):
            required_properties.append(property_name)

    return ToolDescription(
        name=tool_name,
        description=tool_description or "",
        tool_properties=tool_properties,
        required_tool_properties=required_properties,
    )


def get_user_set_port_names(
    session: Session,
    component_instance_id,
) -> set[str]:
    """Return the names of tool-eligible ports configured as USER_SET.

    Used by agent_builder_service to determine which literal field expressions
    should be forwarded as tool_pre_configured_inputs.
    """
    configs = get_tool_port_configurations(session, component_instance_id, eager_load_port_definition=True)
    names: set[str] = set()
    for config in configs:
        if config.setup_mode != PortSetupMode.USER_SET:
            continue
        if config.ai_name_override:
            names.add(config.ai_name_override)
        elif config.port_definition and config.port_definition.name:
            names.add(config.port_definition.name)
        elif config.input_port_instance and config.input_port_instance.name:
            names.add(config.input_port_instance.name)
    return names
