import uuid
import json

from ada_backend.database.models import BasicParameter, ComponentParameterDefinition, Component, ComponentInstance
from ada_backend.database.seed.utils import COMPONENT_UUIDS


def create_input_component(session, name: str = "API Input") -> ComponentInstance:
    """Creates a new input component instance"""
    # First get or create the input component
    input_component = session.query(Component).filter(Component.id == COMPONENT_UUIDS["input"]).first()
    # Fetch parameter definitions for this component
    parameter_definitions = (
        session.query(ComponentParameterDefinition)
        .filter(ComponentParameterDefinition.component_id == input_component.id)
        .all()
    )

    component_instance_id = uuid.uuid4()
    basic_parameters = [
        BasicParameter(
            id=uuid.uuid4(),
            component_instance_id=component_instance_id,
            parameter_definition_id=definition.id,
            value=definition.default if isinstance(definition.default, str) else json.dumps(definition.default),
            order=index,
        )
        for index, definition in enumerate(parameter_definitions)
    ]

    # Create the component instance
    instance = ComponentInstance(
        id=component_instance_id,  # uuid.uuid4(),  # Generate a new UUID for the instance
        component_id=input_component.id,
        name=name,
        basic_parameters=basic_parameters,
    )

    session.add(instance)
    session.commit()

    return instance
