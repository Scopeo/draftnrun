from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def create_input_port_instance(
    session: Session,
    component_instance_id: UUID,
    name: str,
    port_definition_id: Optional[UUID] = None,
    field_expression_id: Optional[UUID] = None,
    description: Optional[str] = None,
) -> db.InputPortInstance:
    input_port = db.InputPortInstance(
        component_instance_id=component_instance_id,
        name=name,
        port_definition_id=port_definition_id,
        field_expression_id=field_expression_id,
        description=description,
    )
    session.add(input_port)
    session.commit()
    session.refresh(input_port)
    return input_port


def get_input_port_instance(
    session: Session,
    input_port_instance_id: UUID,
) -> Optional[db.InputPortInstance]:
    return session.query(db.InputPortInstance).filter(db.InputPortInstance.id == input_port_instance_id).first()


def get_input_port_instances_for_component_instance(
    session: Session,
    component_instance_id: UUID,
) -> list[db.InputPortInstance]:
    return (
        session.query(db.InputPortInstance)
        .filter(db.InputPortInstance.component_instance_id == component_instance_id)
        .all()
    )


def update_input_port_instance(
    session: Session,
    input_port_instance_id: UUID,
    name: Optional[str] = None,
    port_definition_id: Optional[UUID] = None,
    field_expression_id: Optional[UUID] = None,
    description: Optional[str] = None,
) -> Optional[db.InputPortInstance]:
    input_port = get_input_port_instance(session, input_port_instance_id)
    if not input_port:
        return None

    if name is not None:
        input_port.name = name
    if port_definition_id is not None:
        input_port.port_definition_id = port_definition_id
    if field_expression_id is not None:
        input_port.field_expression_id = field_expression_id
    if description is not None:
        input_port.description = description

    session.add(input_port)
    session.commit()
    session.refresh(input_port)
    return input_port


def delete_input_port_instance(
    session: Session,
    input_port_instance_id: UUID,
) -> bool:
    deleted_count = (
        session.query(db.InputPortInstance).filter(db.InputPortInstance.id == input_port_instance_id).delete()
    )
    if deleted_count > 0:
        session.commit()
        return True
    return False


def delete_input_port_instances_for_component_instance(
    session: Session,
    component_instance_id: UUID,
) -> int:
    deleted_count = (
        session.query(db.InputPortInstance)
        .filter(db.InputPortInstance.component_instance_id == component_instance_id)
        .delete()
    )
    if deleted_count > 0:
        session.commit()
    return deleted_count
