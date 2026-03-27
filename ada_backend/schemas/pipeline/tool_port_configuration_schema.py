"""Schemas for tool port configuration API requests and responses."""

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from ada_backend.database.models import JsonSchemaType, PortSetupMode


class ToolPortConfigurationSchema(BaseModel):
    """Schema for a per-port tool configuration.

    Frontend uses ``parameter_id`` to identify which PortDefinition
    this config applies to (maps to ``port_definition_id`` in the DB).
    Custom ports have ``parameter_id=None`` and use ``ai_name_override``.
    """

    id: Optional[UUID] = None
    component_instance_id: Optional[UUID] = None
    # Links this config row to a concrete InputPortInstance (when available).
    # Optional because configs can also be keyed by port definition only.
    input_port_instance_id: Optional[UUID] = None
    parameter_id: Optional[UUID] = None
    setup_mode: PortSetupMode = PortSetupMode.AI_FILLED
    field_expression_id: Optional[UUID] = None
    expression_json: Optional[Any] = None
    ai_name_override: Optional[str] = None
    ai_description_override: Optional[str] = None
    is_required_override: Optional[bool] = None
    custom_parameter_type: Optional[JsonSchemaType] = None
    custom_ui_component_properties: Optional[Any] = None
    json_schema_override: Optional[Any] = None
