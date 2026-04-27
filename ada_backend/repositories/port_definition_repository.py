from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def get_output_port_definition_id(session: Session, component_version_id: UUID, port_name: str) -> UUID | None:
    """Get port definition ID for OUTPUT port, returns None if not found"""
    result = (
        session
        .query(db.PortDefinition.id)
        .filter_by(component_version_id=component_version_id, name=port_name, port_type=db.PortType.OUTPUT)
        .first()
    )
    return result[0] if result else None


def get_input_port_definition_id(session: Session, component_version_id: UUID, port_name: str) -> UUID | None:
    """Get port definition ID for INPUT port, returns None if not found"""
    result = (
        session
        .query(db.PortDefinition.id)
        .filter_by(component_version_id=component_version_id, name=port_name, port_type=db.PortType.INPUT)
        .first()
    )
    return result[0] if result else None


def is_drives_output_schema_port(session: Session, component_version_id: UUID, port_name: str) -> bool:
    """Return True if the named INPUT port exists and has drives_output_schema=True."""
    result = (
        session
        .query(db.PortDefinition.id)
        .filter_by(
            component_version_id=component_version_id,
            name=port_name,
            port_type=db.PortType.INPUT,
            drives_output_schema=True,
        )
        .first()
    )
    return result is not None


def get_port_definition_by_id(session: Session, port_def_id: UUID) -> db.PortDefinition | None:
    """Get port definition by ID, returns None if not found"""
    return session.query(db.PortDefinition).filter(db.PortDefinition.id == port_def_id).first()


def get_port_definition_default(
    session: Session,
    component_version_id: UUID,
    name: str,
    port_type: db.PortType = db.PortType.INPUT,
) -> str | None:
    return (
        session
        .query(db.PortDefinition.default)
        .filter(
            db.PortDefinition.component_version_id == component_version_id,
            db.PortDefinition.name == name,
            db.PortDefinition.port_type == port_type,
        )
        .scalar()
    )
