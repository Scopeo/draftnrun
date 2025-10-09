import logging

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.services.registry import FACTORY_REGISTRY
from engine.agent.agent import Agent


LOGGER = logging.getLogger(__name__)


def seed_port_definitions(session: Session):
    """
    Seeds or updates port definitions by introspecting Agent classes from the FACTORY_REGISTRY.
    This function performs an upsert operation and cleans up orphaned ports.
    """
    LOGGER.info("Starting to seed/update port definitions from code...")

    # Track which ports should exist for each component
    expected_ports_by_component = {}

    for component_name, factory in FACTORY_REGISTRY._registry.items():
        agent_class = factory.entity_class
        if not issubclass(agent_class, Agent):
            continue

        component_version = (
            session.query(db.ComponentVersion).join(db.Component).filter_by(name=component_name).first()
        )
        if not component_version:
            LOGGER.warning(f"Component '{component_name}' not found in the database for port seeding. Skipping.")
            continue

        LOGGER.info(f"Processing component for ports: {component_version.component.name}")

        try:
            inputs_schema = agent_class.get_inputs_schema()
            outputs_schema = agent_class.get_outputs_schema()
            canonical_ports = agent_class.get_canonical_ports()
        except Exception as e:
            LOGGER.error(f"Could not retrieve schemas for {component_name}: {e}")
            continue

        # Track expected ports for this component
        expected_ports = set()
        for field_name in inputs_schema.model_fields.keys():
            expected_ports.add((field_name, db.PortType.INPUT))
        for field_name in outputs_schema.model_fields.keys():
            expected_ports.add((field_name, db.PortType.OUTPUT))

        expected_ports_by_component[component.id] = expected_ports

        # Upsert input ports
        for field_name, field_info in inputs_schema.model_fields.items():
            port = (
                session.query(db.PortDefinition)
                .filter_by(component_version_id=component_version.id, name=field_name, port_type=db.PortType.INPUT)
                .first()
            )
            is_canonical = canonical_ports.get("input") == field_name
            if port:
                port.is_canonical = is_canonical
                port.description = field_info.description
                LOGGER.info(f"  - Updating INPUT port: {field_name}")
            else:
                port = db.PortDefinition(
                    component_version_id=component_version.id,
                    name=field_name,
                    port_type=db.PortType.INPUT,
                    is_canonical=is_canonical,
                    description=field_info.description,
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
            if port:
                port.is_canonical = is_canonical
                port.description = field_info.description
                LOGGER.info(f"  - Updating OUTPUT port: {field_name}")
            else:
                port = db.PortDefinition(
                    component_version_id=component_version.id,
                    name=field_name,
                    port_type=db.PortType.OUTPUT,
                    is_canonical=is_canonical,
                    description=field_info.description,
                )
                session.add(port)
                LOGGER.info(f"  - Creating OUTPUT port: {field_name}")

    LOGGER.info("Cleaning up orphaned port definitions...")
    for component_id, expected_ports in expected_ports_by_component.items():
        existing_ports = session.query(db.PortDefinition).filter_by(component_id=component_id).all()
        for port in existing_ports:
            port_key = (port.name, port.port_type)
            if port_key not in expected_ports:
                LOGGER.info(f"  - Deleting orphaned port: {port.name} ({port.port_type})")
                session.delete(port)

    session.commit()
