import uuid
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ada_backend.database.models import (
    Component,
    ComponentParameterDefinition,
    BasicParameter,
    ComponentInstance,
)
from ada_backend.database.seed.utils import COMPONENT_UUIDS


async def create_input_component(session: AsyncSession, name: str = "Input") -> ComponentInstance:
    """Creates a new input component instance asynchronously."""

    # Fetch the input component
    result = await session.execute(
        select(Component).filter(Component.id == COMPONENT_UUIDS["input"])
    )
    input_component = result.scalar_one_or_none()
    if input_component is None:
        raise ValueError("Input component not found in DB")

    # Fetch parameter definitions
    result = await session.execute(
        select(ComponentParameterDefinition).filter(
            ComponentParameterDefinition.component_id == input_component.id
        )
    )
    parameter_definitions = result.scalars().all()

    # Generate new component instance ID
    component_instance_id = uuid.uuid4()

    # Create parameters
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

    # Create component instance
    instance = ComponentInstance(
        id=component_instance_id,
        component_id=input_component.id,
        name=name,
        basic_parameters=basic_parameters,
    )

    session.add(instance)
    await session.commit()
    return instance
