from typing import Optional, List
from uuid import UUID
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload

from ada_backend.database import models as db
from ada_backend.database.models import ParameterType, UIComponent
from ada_backend.schemas.components_schema import ComponentWithParametersDTO, SubComponentParamSchema
from ada_backend.schemas.parameter_schema import ComponentParamDefDTO
from engine.agent.agent import ToolDescription

LOGGER = logging.getLogger(__name__)


@dataclass
class InstanceParameterWithDefinition:
    name: str
    value: str
    type: ParameterType
    nullable: bool
    default: Optional[str] = None
    ui_component: Optional[UIComponent] = None
    ui_component_properties: Optional[dict] = None
    is_advanced: bool = False


# --- READ operations ---
async def get_component_by_id(
    session: AsyncSession,
    component_id: UUID,
) -> Optional[db.Component]:
    """
    Retrieves a specific component by its ID asynchronously.
    """
    stmt = select(db.Component).where(db.Component.id == component_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_component_by_name(
    session: AsyncSession,
    name: str,
) -> Optional[db.Component]:
    """
    Retrieves a specific component by its name asynchronously.
    """
    stmt = select(db.Component).where(db.Component.name == name)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_component_parameter_definition_by_component_id(
    session: AsyncSession,
    component_id: UUID,
) -> list[db.ComponentParameterDefinition]:
    """
    Retrieves all parameter definitions for a given component asynchronously.
    """
    stmt = select(db.ComponentParameterDefinition).where(
        db.ComponentParameterDefinition.component_id == component_id
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_subcomponent_param_def_by_component_id(
    session: AsyncSession,
    component_id: UUID,
) -> list[tuple[db.ComponentParameterDefinition, db.ComponentParameterChildRelationship]]:
    """
    Retrieves subcomponent parameter definitions for a given component asynchronously.
    """
    stmt = (
        select(db.ComponentParameterDefinition, db.ComponentParameterChildRelationship)
        .join(
            db.ComponentParameterChildRelationship,
            db.ComponentParameterChildRelationship.component_parameter_definition_id
            == db.ComponentParameterDefinition.id,
        )
        .where(
            db.ComponentParameterDefinition.component_id == component_id,
            db.ComponentParameterDefinition.type == ParameterType.COMPONENT,
        )
    )
    result = await session.execute(stmt)
    return result.all()


async def get_component_instance_by_id(session: AsyncSession, instance_id: UUID) -> Optional[db.ComponentInstance]:
    stmt = (
        select(db.ComponentInstance)
        .options(selectinload(db.ComponentInstance.component))
        .where(db.ComponentInstance.id == instance_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_component_basic_parameters(
    session: AsyncSession,
    component_instance_id: UUID,
) -> list[db.BasicParameter]:
    """
    Retrieves all basic parameters for a given component instance asynchronously,
    eagerly loading related ParameterDefinition and OrganizationSecret models.
    """
    stmt = (
        select(db.BasicParameter)
        .where(db.BasicParameter.component_instance_id == component_instance_id)
        .options(selectinload(db.BasicParameter.parameter_definition))
        .options(selectinload(db.BasicParameter.organization_secret))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_instance_parameters_with_definition(
    session: AsyncSession,
    component_instance_id: UUID,
) -> list[InstanceParameterWithDefinition]:
    """
    Retrieves all parameters for a given component instance with their definitions asynchronously.
    """
    stmt = (
        select(db.BasicParameter, db.ComponentParameterDefinition)
        .join(
            db.ComponentParameterDefinition,
            db.BasicParameter.parameter_definition_id == db.ComponentParameterDefinition.id,
        )
        .where(
            db.BasicParameter.component_instance_id == component_instance_id,
        )
    )
    result = await session.execute(stmt)
    results = result.all()

    return [
        InstanceParameterWithDefinition(
            name=param_def.name,
            value=param.value,
            type=param_def.type,
            nullable=param_def.nullable,
            default=param_def.default,
            ui_component=param_def.ui_component,
            ui_component_properties=param_def.ui_component_properties,
            is_advanced=param_def.is_advanced,
        )
        for param, param_def in results
    ]


async def get_component_sub_components(
    session: AsyncSession,
    component_instance_id: UUID,
) -> list[db.ComponentSubInput]:
    """
    Retrieves the child component instances and their parameter definitions
    for a given parent component instance asynchronously.
    """
    stmt = (
        select(db.ComponentSubInput)
        .where(db.ComponentSubInput.parent_component_instance_id == component_instance_id)
        .options(
            joinedload(db.ComponentSubInput.parameter_definition),  # Eager load parameter_definition
            joinedload(db.ComponentSubInput.child_component_instance)
        )
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_tool_description(
    session: AsyncSession,
    component_instance_id: UUID,
) -> Optional[db.ToolDescription]:
    """
    Retrieves the tool description associated with a specific component instance asynchronously.
    """
    stmt = (
        select(db.ToolDescription)
        .join(
            db.ComponentInstance,
            db.ComponentInstance.tool_description_id == db.ToolDescription.id,
        )
        .where(db.ComponentInstance.id == component_instance_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_tool_description_component(
    session: AsyncSession,
    component_id: UUID,
) -> Optional[db.ToolDescription]:
    """
    Retrieves the tool description associated with a specific component asynchronously.
    """
    stmt = (
        select(db.ToolDescription)
        .join(
            db.Component,
            db.Component.default_tool_description_id == db.ToolDescription.id,
        )
        .where(db.Component.id == component_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_tool_parameter_by_component_id(
    session: AsyncSession,
    component_id: UUID,
) -> Optional[db.ComponentParameterDefinition]:
    """
    Retrieves the tool component associated with a specific component instance asynchronously.
    """
    stmt = select(db.ComponentParameterDefinition).where(
        db.ComponentParameterDefinition.component_id == component_id,
        db.ComponentParameterDefinition.type == ParameterType.TOOL,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_components_with_parameters(
    session: AsyncSession,
) -> List[ComponentWithParametersDTO]:
    """
    Retrieves all components and their parameter definitions from the database asynchronously.
    Component type parameters are moved to the tools list, while other parameters
    remain in the parameters list.

    Args:
        session (AsyncSession): SQLAlchemy asynchronous session.

    Returns:
        List[ComponentWithParametersDTO]: A list of DTOs containing components,
        their tools (component parameters) and other parameter definitions.
    """
    # Get all components
    stmt_components = select(db.Component)
    result_components = await session.execute(stmt_components)
    components = result_components.scalars().all()

    # For each component, get its parameter definitions and build result
    result = []
    for component in components:
        parameters = await get_component_parameter_definition_by_component_id(
            session,
            component.id,
        )

        subcomponent_params = await get_subcomponent_param_def_by_component_id(
            session,
            component.id,
        )

        parameters_to_fill = []
        tool_param_name = None
        for param in parameters:
            if param.type == ParameterType.TOOL:
                if tool_param_name is None:
                    tool_param_name = param.name
                else:
                    raise ValueError(
                        f"Multiple tool parameters found for component {component.name}: "
                        f"{tool_param_name}, {param.name}"
                    )
            elif param.type != ParameterType.COMPONENT:
                parameters_to_fill.append(
                    ComponentParamDefDTO(
                        id=param.id,
                        component_id=param.component_id,
                        name=param.name,
                        type=param.type,
                        nullable=param.nullable,
                        default=param.default,
                        ui_component=param.ui_component,
                        ui_component_properties=param.ui_component_properties,
                        is_advanced=param.is_advanced,
                        order=param.order,
                    )
                )

        default_tool_description_db = await get_tool_description_component(session=session, component_id=component.id)
        tool_description = (
            ToolDescription(
                name=default_tool_description_db.name,
                description=default_tool_description_db.description,
                tool_properties=default_tool_description_db.tool_properties,
                required_tool_properties=default_tool_description_db.required_tool_properties,
            ).model_dump()
            if default_tool_description_db
            else None
        )
        # Create ComponentWithParametersDTO
        result.append(
            ComponentWithParametersDTO(
                id=component.id,
                name=component.name,
                description=component.description,
                is_agent=component.is_agent,
                tool_parameter_name=tool_param_name,
                function_callable=component.function_callable,
                release_stage=component.release_stage,
                can_use_function_calling=component.can_use_function_calling,
                tool_description=tool_description,
                parameters=parameters_to_fill,
                subcomponents_info=[
                    SubComponentParamSchema(
                        id=param_child_def.child_component_id,
                        parameter_name=subcomponent_param.name,
                        is_optional=subcomponent_param.nullable,
                    )
                    for subcomponent_param, param_child_def in subcomponent_params
                ],
            )
        )

    return result


async def insert_component_parameter_definition(
    session: AsyncSession,
    component_id: UUID,
    name: str,
    param_type: ParameterType,
    nullable: bool,
    default: Optional[str] = None,
    subinput_component_id: Optional[UUID] = None,
    ui_component: Optional[UIComponent] = None,
    ui_component_properties: Optional[dict] = None,
) -> db.ComponentParameterDefinition:
    """
    Inserts a new component parameter definition into the database asynchronously.
    """
    component_parameter_definition = db.ComponentParameterDefinition(
        component_id=component_id,
        name=name,
        type=param_type,
        nullable=nullable,
        default=default,
        subinput_component_id=subinput_component_id,
        ui_component=ui_component,
        ui_component_properties=ui_component_properties,
    )
    session.add(component_parameter_definition)
    await session.commit()
    await session.refresh(component_parameter_definition)
    return component_parameter_definition


async def upsert_component_instance(
    session: AsyncSession,
    component_id: UUID,
    name: Optional[str] = None,
    ref: Optional[str] = None,
    tool_description_id: Optional[UUID] = None,
    id_: Optional[UUID] = None,
) -> db.ComponentInstance:
    """
    Inserts or updates a component instance in the database.
    If id_ is provided, performs an upsert operation.
    If id_ is not provided, creates a new instance.
    """
    LOGGER.info(f"[UPSERT] Starting for ID: {id_}")

    if not component_id:
        raise ValueError(
            "Impossible to create a component instance without a component",
        )

    if id_ is None:
        LOGGER.info("ID IS NONE - Creating new ComponentInstance.")
        new_component_instance = db.ComponentInstance(
            component_id=component_id,
            name=name,
            ref=ref,
            tool_description_id=tool_description_id,
        )
        session.add(new_component_instance)
        await session.commit()
        await session.refresh(new_component_instance)
        final_persistent_instance = new_component_instance
        LOGGER.info(f"[UPSERT] Created ComponentInstance ID: {final_persistent_instance.id}")

    else:
        LOGGER.info(f"MERGE BECAUSE ID {id_} - Attempting to update existing ComponentInstance.")
        transient_instance_for_merge = db.ComponentInstance(
            id=id_,
            component_id=component_id,
            name=name,
            ref=ref,
            tool_description_id=tool_description_id,
        )
        final_persistent_instance = await session.merge(transient_instance_for_merge)
        await session.commit()
        LOGGER.info(f"[UPSERT] Merged ComponentInstance ID: {final_persistent_instance.id}")

    stmt = (
        select(db.ComponentInstance)
        .options(selectinload(db.ComponentInstance.component))
        .where(db.ComponentInstance.id == final_persistent_instance.id)
    )
    result = await session.execute(stmt)
    instance = result.scalar_one_or_none()

    if not instance:
        LOGGER.error(f"[UPSERT] Instance with ID {final_persistent_instance.id} could not be reloaded after upsert operation.")
        raise RuntimeError(f"ComponentInstance with ID {final_persistent_instance.id} not found after upsert.")

    LOGGER.info(f"[UPSERT] Successfully returned ComponentInstance with ID: {instance.id}")
    return instance


async def upsert_basic_parameter(
    session: AsyncSession,
    component_instance_id: UUID,
    parameter_definition_id: UUID,
    value: Optional[str] = None,
    order: Optional[int] = None,
    org_secret_id: Optional[UUID] = None,
) -> db.BasicParameter:
    """
    Inserts or updates a basic parameter asynchronously. If a parameter with the same
    component_instance_id and parameter_definition_id exists, updates it.
    """
    if value is None and org_secret_id is None:
        raise ValueError(
            "Either value or org_secret_id must be provided for a basic parameter.",
        )

    if value and org_secret_id:
        raise ValueError(
            "Cannot set both value and org_secret_id for a basic parameter. " "Use one or the other.",
        )

    stmt = select(db.BasicParameter).where(
        db.BasicParameter.component_instance_id == component_instance_id,
        db.BasicParameter.parameter_definition_id == parameter_definition_id,
        db.BasicParameter.order == order,
    )
    parameter = (await session.execute(stmt)).scalar_one_or_none()

    if org_secret_id:
        if parameter:
            parameter.organization_secret_id = org_secret_id
        else:
            parameter = db.BasicParameter(
                component_instance_id=component_instance_id,
                parameter_definition_id=parameter_definition_id,
                organization_secret_id=org_secret_id,
                order=order,
            )
            session.add(parameter)

    else:
        if parameter:
            parameter.value = value
        else:
            parameter = db.BasicParameter(
                component_instance_id=component_instance_id,
                parameter_definition_id=parameter_definition_id,
                value=value,
                order=order,
            )
            session.add(parameter)
    await session.commit()
    await session.refresh(parameter)
    return parameter


async def upsert_sub_component_input(
    session: AsyncSession,
    parent_component_instance_id: UUID,
    child_component_instance_id: UUID,
    parameter_definition_id: UUID,
    order: Optional[int] = None,
) -> db.ComponentSubInput:
    """
    Upserts a sub-component input relationship into the database asynchronously.
    If a relationship with the same parent, child, and parameter definition exists,
    it will be updated (PUT behavior).

    Args:
        session (AsyncSession): SQLAlchemy asynchronous session.
        parent_component_instance_id (UUID): ID of the parent component instance.
        child_component_instance_id (UUID): ID of the child component instance.
        parameter_definition_id (UUID): ID of the parameter definition.
        order (Optional[int]): Optional order value.

    Returns:
        db.ComponentSubInput: The created or updated relationship object.
    """
    stmt = select(db.ComponentSubInput).where(
        db.ComponentSubInput.parent_component_instance_id == parent_component_instance_id,
        db.ComponentSubInput.child_component_instance_id == child_component_instance_id,
        db.ComponentSubInput.parameter_definition_id == parameter_definition_id,
    )
    sub_input = (await session.execute(stmt)).scalar_one_or_none()

    if sub_input:
        # Update existing relationship
        sub_input.order = order
    else:
        # Create new relationship
        sub_input = db.ComponentSubInput(
            parent_component_instance_id=parent_component_instance_id,
            child_component_instance_id=child_component_instance_id,
            parameter_definition_id=parameter_definition_id,
            order=order,
        )
        session.add(sub_input)

    await session.commit()
    await session.refresh(sub_input)
    return sub_input


async def upsert_tool_description(
    session: AsyncSession,
    name: str,
    description: str,
    tool_properties: dict,
    required_tool_properties: list[str],
) -> db.ToolDescription:
    """
    Inserts or updates a tool description in the database asynchronously.
    Uses name as unique identifier for upsert operation.
    Follows PUT semantics - completely replaces existing tool description.

    Returns:
        db.ToolDescription: The created or updated tool description object.
    """
    stmt = select(db.ToolDescription).where(db.ToolDescription.name == name)
    tool_description = (await session.execute(stmt)).scalar_one_or_none()

    if tool_description:
        # Update existing tool description (PUT behavior)
        tool_description.description = description
        tool_description.tool_properties = tool_properties
        tool_description.required_tool_properties = required_tool_properties
    else:
        # Create new tool description
        tool_description = db.ToolDescription(
            name=name,
            description=description,
            tool_properties=tool_properties,
            required_tool_properties=required_tool_properties,
        )
        session.add(tool_description)

    await session.commit()
    await session.refresh(tool_description)
    return tool_description


# --- DELETE operations ---
async def delete_component_instances(
    session: AsyncSession,
    component_instance_ids: list[UUID],
) -> None:
    """
    Deletes all component instances for a given component asynchronously.
    Ensures cascading deletes on related entities.
    """

    if not component_instance_ids:
        LOGGER.warning("No component instances to delete.")
        return

    LOGGER.info(f"Deleting component instances with IDs: {component_instance_ids}")
    stmt = select(db.ComponentInstance).where(db.ComponentInstance.id.in_(component_instance_ids))
    result = await session.execute(stmt)
    instances = result.scalars().all()

    for instance in instances:
        await session.delete(instance)  # Triggers ORM cascade

    await session.commit()


async def delete_component_instance_parameters(
    session: AsyncSession,
    component_instance_id: UUID,
) -> None:
    """
    Deletes all parameters for a given component instance asynchronously.
    """
    LOGGER.info(f"Deleting parameters for component instance {component_instance_id}")
    stmt = select(db.BasicParameter).where(db.BasicParameter.component_instance_id == component_instance_id)
    result = await session.execute(stmt)
    parameters = result.scalars().all()
    for param in parameters:
        await session.delete(param)
    await session.commit()
