from typing import Optional
import uuid
import json

from sqlalchemy.orm import Session

from ada_backend.database.models import (
    BasicParameter,
    ComponentInstance,
    ComponentParameterDefinition,
    ParameterType,
)
from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS


def create_component_instance(
    session: Session, component_version_id: uuid.UUID, name: str, component_instance_id: Optional[uuid.UUID] = None
) -> ComponentInstance:
    """
    Creates a new component instance for the given component ID.

    Args:
        session (Session): SQLAlchemy session
        component_id (UUID): ID of the component to instantiate
        name (str): Name of the component instance

    Returns:
        ComponentInstance: The created component instance
    """
    # Fetch parameter definitions for this component
    parameter_definitions = (
        session.query(ComponentParameterDefinition)
        .filter(ComponentParameterDefinition.component_version_id == component_version_id)
        .all()
    )

    component_instance_id = component_instance_id or uuid.uuid4()
    basic_parameters = [
        BasicParameter(
            id=uuid.uuid4(),
            component_instance_id=component_instance_id,
            parameter_definition_id=definition.id,
            value=definition.default if isinstance(definition.default, str) else json.dumps(definition.default),
        )
        for definition in parameter_definitions
        if definition.type
        not in [
            ParameterType.COMPONENT,
            ParameterType.TOOL,
            ParameterType.LLM_API_KEY,
            ParameterType.SECRETS,
            ParameterType.DATA_SOURCE,
        ]
    ]

    instance = ComponentInstance(
        id=component_instance_id,  # uuid.uuid4(),  # Generate a new UUID for the instance
        component_version_id=component_version_id,
        name=name,
        basic_parameters=basic_parameters,
    )
    session.add(instance)
    session.commit()
    return instance


# TODO: move to service
def create_input_component(session: Session, name: str = "Start") -> ComponentInstance:
    """Creates a new input component instance"""
    component_version_id = COMPONENT_VERSION_UUIDS["start_v2"]
    return create_component_instance(session, component_version_id=component_version_id, name=name)
