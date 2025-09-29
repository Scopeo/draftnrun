from typing import Optional
import uuid
import json

from sqlalchemy.orm import Session

from ada_backend.database.models import (
    BasicParameter,
    Component,
    ComponentInstance,
    ParameterType,
)
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.repositories.component_repository import get_component_parameter_definition_by_component_id


def create_component_instance(
    session: Session, component_id: uuid.UUID, name: str, component_instance_id: Optional[uuid.UUID] = None
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
    component = session.query(Component).filter(Component.id == component_id).first()
    # Fetch parameter definitions for this component
    parameter_definitions = get_component_parameter_definition_by_component_id(session, component_id)

    if component_instance_id is None:
        component_instance_id = uuid.uuid4()
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
        id=component_instance_id,
        component_id=component.id,
        name=name,
        basic_parameters=basic_parameters,
    )
    session.add(instance)
    session.commit()
    return instance


def create_input_component(session: Session, name: str = "API Input") -> ComponentInstance:
    """Creates a new input component instance"""
    return create_component_instance(session, COMPONENT_UUIDS["input"], name)
