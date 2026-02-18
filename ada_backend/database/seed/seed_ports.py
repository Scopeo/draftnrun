import logging
import sys
import types
from enum import Enum
from typing import Union, get_args, get_origin

from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.services.registry import FACTORY_REGISTRY
from engine.components.component import Component

LOGGER = logging.getLogger(__name__)


def get_parameter_type(field_info: FieldInfo) -> db.ParameterType:
    extra = getattr(field_info, "json_schema_extra", None)
    if isinstance(extra, dict) and "parameter_type" in extra:
        param_type_value = extra["parameter_type"]
        try:
            return db.ParameterType(param_type_value)
        except ValueError:
            LOGGER.warning(
                "Invalid parameter_type found in component metadata. Falling back to STRING.",
                invalid_parameter_type=param_type_value,
            )

    return db.ParameterType.STRING


def get_field_default(field_info: FieldInfo) -> str | None:
    if field_info.default is PydanticUndefined:
        return None
    value = field_info.default
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def is_field_nullable(field_info: FieldInfo) -> bool:
    """Determine if a Pydantic field can accept None.

    A field is nullable if its type annotation includes NoneType.
    This is orthogonal to whether the field is required (has a default).

    Handles both:
    - typing.Union syntax: Optional[T] or Union[T, None]
    - PEP 604 syntax (Python 3.10+): T | None
    """

    annotation = field_info.annotation

    if annotation is type(None):
        return True

    origin = get_origin(annotation)

    # typing.Union (for Optional[T] or Union[T, None])
    if origin is Union:
        args = get_args(annotation)
        return type(None) in args

    # types.UnionType (for X | None syntax on Python 3.10+)
    if sys.version_info >= (3, 10):
        if origin is types.UnionType:
            args = get_args(annotation)
            return type(None) in args

    # For other types (e.g., str, int, list), they're not nullable
    return False


def seed_port_definitions(session: Session):
    """
    Seeds or updates port definitions by introspecting Agent classes from the FACTORY_REGISTRY.
    This function performs an upsert operation and cleans up orphaned ports.
    """
    LOGGER.info("Starting to seed/update port definitions from code...")

    # Track which ports should exist for each component
    expected_ports_by_component_version = {}

    for component_version_id, factory in FACTORY_REGISTRY._registry.items():
        agent_class = factory.entity_class
        if not issubclass(agent_class, Component):
            continue

        component_version = session.query(db.ComponentVersion).filter_by(id=component_version_id).first()
        if not component_version:
            LOGGER.warning(
                f"Component version ID '{component_version_id}' not found in the database for port seeding. Skipping."
            )
            continue

        LOGGER.info(f"Processing component for ports: {component_version.component.name}")

        try:
            inputs_schema = agent_class.get_inputs_schema()
            outputs_schema = agent_class.get_outputs_schema()
            canonical_ports = agent_class.get_canonical_ports()
        except Exception as e:
            LOGGER.error(f"Could not retrieve schemas for {component_version.component.name}: {e}")
            continue

        # Track expected ports for this component
        expected_ports = set()

        for field_name, field_info in inputs_schema.model_fields.items():
            extra = getattr(field_info, "json_schema_extra", None)
            if isinstance(extra, dict) and extra.get("disabled_as_input"):
                LOGGER.info(f"  - Skipping disabled INPUT port: {field_name}")
                continue
            expected_ports.add((field_name, db.PortType.INPUT))

        for field_name in outputs_schema.model_fields.keys():
            expected_ports.add((field_name, db.PortType.OUTPUT))

        expected_ports_by_component_version[component_version.id] = expected_ports

        # Upsert input ports
        for field_name, field_info in inputs_schema.model_fields.items():
            extra = getattr(field_info, "json_schema_extra", None)

            if isinstance(extra, dict) and extra.get("disabled_as_input"):
                LOGGER.info(f"  - Skipping disabled INPUT port: {field_name}")
                continue

            port = (
                session.query(db.PortDefinition)
                .filter_by(component_version_id=component_version.id, name=field_name, port_type=db.PortType.INPUT)
                .first()
            )
            is_canonical = canonical_ports.get("input") == field_name
            ui_component = None
            ui_component_properties = None
            if isinstance(extra, dict):
                ui_component = extra.get("ui_component")
                ui_component_properties = extra.get("ui_component_properties")

            port_description = field_info.description
            parameter_type = get_parameter_type(field_info)
            is_nullable = is_field_nullable(field_info)
            field_default = get_field_default(field_info)

            # Every input should have a UI component and at least a basic label,
            # so synthesized input-parameters are always renderable in the UI.
            is_migrated = getattr(agent_class, "migrated", False)
            if is_migrated:
                if ui_component is None:
                    ui_component = db.UIComponent.TEXTFIELD
                if not ui_component_properties:
                    ui_component_properties = {
                        "label": field_name.replace("_", " ").title(),
                    }
                if port_description and "description" not in ui_component_properties:
                    ui_component_properties["description"] = port_description
                # TODO: Temporary patch to ensure 'messages' input is readonly. Clean later.
                if field_name == "messages":
                    ui_component_properties["readonly"] = True
                    ui_component_properties["alert_message"] = (
                        "This field is automatically filled with the output of the previous component"
                    )
            else:
                LOGGER.info(f"  - Skipping UI component for non-migrated component: {agent_class.__name__}")

            if port:
                port.is_canonical = is_canonical
                port.description = port_description
                port.parameter_type = parameter_type
                port.ui_component = ui_component
                port.ui_component_properties = ui_component_properties
                port.nullable = is_nullable
                port.default = field_default
                LOGGER.info(f"  - Updating INPUT port: {field_name}")
            else:
                port = db.PortDefinition(
                    component_version_id=component_version.id,
                    name=field_name,
                    port_type=db.PortType.INPUT,
                    is_canonical=is_canonical,
                    description=port_description,
                    parameter_type=parameter_type,
                    ui_component=ui_component,
                    ui_component_properties=ui_component_properties,
                    nullable=is_nullable,
                    default=field_default,
                )
                session.add(port)
                LOGGER.info(f"  - Creating INPUT port: {field_name}")

        # Upsert output ports
        for field_name, field_info in outputs_schema.model_fields.items():
            port = (
                session.query(db.PortDefinition)
                .filter_by(component_version_id=component_version.id, name=field_name, port_type=db.PortType.OUTPUT)
                .first()
            )
            is_canonical = canonical_ports.get("output") == field_name
            parameter_type = get_parameter_type(field_info)
            is_nullable = is_field_nullable(field_info)

            if port:
                port.is_canonical = is_canonical
                port.description = field_info.description
                port.parameter_type = parameter_type
                port.nullable = is_nullable
                LOGGER.info(f"  - Updating OUTPUT port: {field_name}")
            else:
                port = db.PortDefinition(
                    component_version_id=component_version.id,
                    name=field_name,
                    port_type=db.PortType.OUTPUT,
                    is_canonical=is_canonical,
                    description=field_info.description,
                    parameter_type=parameter_type,
                    nullable=is_nullable,
                )
                session.add(port)
                LOGGER.info(f"  - Creating OUTPUT port: {field_name}")

    LOGGER.info("Cleaning up orphaned port definitions...")
    for component_version_id, expected_ports in expected_ports_by_component_version.items():
        existing_ports = session.query(db.PortDefinition).filter_by(component_version_id=component_version_id).all()
        for port in existing_ports:
            port_key = (port.name, port.port_type)
            if port_key not in expected_ports:
                LOGGER.info(f"  - Deleting orphaned port: {port.name} ({port.port_type})")
                session.delete(port)

    session.commit()
