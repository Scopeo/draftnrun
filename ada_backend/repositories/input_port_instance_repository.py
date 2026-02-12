from typing import Optional, Union
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from ada_backend.database import models as db

# Sentinel value to distinguish between "not provided" and "explicitly None"
_UNSET = object()


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
    eager_load_field_expression: bool = False,
) -> list[db.InputPortInstance]:
    query = session.query(db.InputPortInstance).filter(
        db.InputPortInstance.component_instance_id == component_instance_id
    )

    if eager_load_field_expression:
        query = query.options(joinedload(db.InputPortInstance.field_expression))

    return query.all()


def update_input_port_instance(
    session: Session,
    input_port_instance_id: UUID,
    name: Union[str, object] = _UNSET,
    port_definition_id: Union[UUID, None, object] = _UNSET,
    field_expression_id: Union[UUID, None, object] = _UNSET,
    description: Union[str, None, object] = _UNSET,
) -> Optional[db.InputPortInstance]:
    """Update an input port instance.

    Uses a sentinel value pattern to distinguish between:
    - Not updating a field (parameter not provided / _UNSET)
    - Explicitly setting a field to None (parameter = None)
    - Setting a field to a value (parameter = value)

    Examples:
        update_input_port_instance(session, id)
            # Updates nothing
        update_input_port_instance(session, id, field_expression_id=None)
            # Explicitly clears the field expression
        update_input_port_instance(session, id, field_expression_id=some_uuid)
            # Sets a new field expression
    """
    input_port = get_input_port_instance(session, input_port_instance_id)
    if not input_port:
        return None

    if name is not _UNSET:
        input_port.name = name
    if port_definition_id is not _UNSET:
        input_port.port_definition_id = port_definition_id
    if field_expression_id is not _UNSET:
        input_port.field_expression_id = field_expression_id
    if description is not _UNSET:
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
