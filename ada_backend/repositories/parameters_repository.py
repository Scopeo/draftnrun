from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db


def get_specific_basic_parameter(
    session: Session, component_instance_id: UUID, parameter_definition_id: UUID
) -> db.BasicParameter:
    """
    Retrieves a basic parameter associated with a given component instance and parameter definition ID.

    Args:
        session (Session): SQLAlchemy session.
        component_instance_id (UUID): ID of the component instance.
        parameter_definition_id (UUID): ID of the parameter definition.

    Returns:
        db.BasicParameter: The BasicParameter object, or None if not found.
    """
    return (
        session.query(db.BasicParameter)
        .filter(
            db.BasicParameter.component_instance_id == component_instance_id,
            db.BasicParameter.parameter_definition_id == parameter_definition_id,
        )
        .first()
    )
