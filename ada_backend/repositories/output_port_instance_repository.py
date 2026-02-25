from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def create_output_port_instance(
    session: Session,
    component_instance_id: UUID,
    name: str,
    port_definition_id: Optional[UUID] = None,
) -> db.OutputPortInstance:
    output_port = db.OutputPortInstance(
        component_instance_id=component_instance_id,
        name=name,
        port_definition_id=port_definition_id,
    )
    session.add(output_port)
    session.commit()
    session.refresh(output_port)
    return output_port


def get_output_port_instances_for_component_instance(
    session: Session,
    component_instance_id: UUID,
) -> list[db.OutputPortInstance]:
    return (
        session.query(db.OutputPortInstance)
        .filter(db.PortInstance.component_instance_id == component_instance_id)
        .all()
    )


def get_output_port_instance_by_name(
    session: Session,
    component_instance_id: UUID,
    name: str,
) -> Optional[db.OutputPortInstance]:
    return (
        session.query(db.OutputPortInstance)
        .filter(
            db.PortInstance.component_instance_id == component_instance_id,
            db.PortInstance.name == name,
        )
        .first()
    )


def delete_output_port_instances_for_component_instance(
    session: Session,
    component_instance_id: UUID,
) -> int:
    deleted = (
        session.query(db.PortInstance)
        .filter(
            db.PortInstance.component_instance_id == component_instance_id,
            db.PortInstance.type == db.PortType.OUTPUT,
        )
        .delete(synchronize_session=False)
    )
    if deleted > 0:
        session.commit()
    return deleted
