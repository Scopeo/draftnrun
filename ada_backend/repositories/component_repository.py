from typing import Optional, List
from uuid import UUID
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ParameterType, ReleaseStage, UIComponent
from ada_backend.repositories.categories_repository import get_categories
from ada_backend.repositories.integration_repository import (
    delete_linked_integration,
    get_component_instance_integration_relationship,
    get_integration,
)
from ada_backend.schemas.components_schema import ComponentWithParametersDTO, SubComponentParamSchema
from ada_backend.schemas.integration_schema import IntegrationSchema
from ada_backend.schemas.parameter_schema import ComponentParamDefDTO
from engine.agent.data_structures import ToolDescription

LOGGER = logging.getLogger(__name__)


@dataclass
class InstanceParameterWithDefinition:
    id: UUID
    name: str
    value: str
    type: ParameterType
    nullable: bool
    default: Optional[str] = None
    ui_component: Optional[UIComponent] = None
    ui_component_properties: Optional[dict] = None
    is_advanced: bool = False


# --- READ operations ---
def get_component_by_id(
    session: Session,
    component_id: UUID,
) -> Optional[db.Component]:
    """
    Retrieves a specific component by its ID.
    """
    return (
        session.query(db.Component)
        .filter(
            db.Component.id == component_id,
        )
        .first()
    )


def get_component_by_name(
    session: Session,
    name: str,
) -> Optional[db.Component]:
    """
    Retrieves a specific component by its name.
    """
    return (
        session.query(db.Component)
        .filter(
            db.Component.name == name,
        )
        .first()
    )


def get_component_parameter_definition_by_component_id(
    session: Session,
    component_id: UUID,
) -> list[db.ComponentParameterDefinition]:
    """
    Retrieves all parameter definitions for a given component.
    """
    return (
        session.query(db.ComponentParameterDefinition)
        .filter(
            db.ComponentParameterDefinition.component_id == component_id,
        )
        .all()
    )


def get_subcomponent_param_def_by_component_id(
    session: Session,
    component_id: UUID,
) -> list[tuple[db.ComponentParameterDefinition, db.ComponentParameterChildRelationship]]:
    return (
        session.query(db.ComponentParameterDefinition, db.ComponentParameterChildRelationship)
        .join(
            db.ComponentParameterChildRelationship,
            db.ComponentParameterChildRelationship.component_parameter_definition_id
            == db.ComponentParameterDefinition.id,
        )
        .filter(
            db.ComponentParameterDefinition.component_id == component_id,
            db.ComponentParameterDefinition.type == ParameterType.COMPONENT,
        )
        .all()
    )


def get_component_instance_by_id(
    session: Session,
    component_instance_id: UUID,
) -> Optional[db.ComponentInstance]:
    """
    Retrieves a specific component instance by its ID.
    """
    return (
        session.query(db.ComponentInstance)
        .filter(
            db.ComponentInstance.id == component_instance_id,
        )
        .first()
    )


def get_component_basic_parameters(
    session: Session,
    component_instance_id: UUID,
) -> list[db.BasicParameter]:
    """
    Retrieves all basic parameters for a given component instance.
    """
    return (
        session.query(db.BasicParameter)
        .filter(
            db.BasicParameter.component_instance_id == component_instance_id,
        )
        .all()
    )


def get_instance_parameters_with_definition(
    session: Session,
    component_instance_id: UUID,
) -> list[InstanceParameterWithDefinition]:
    """
    Retrieves all parameters for a given component instance with their definitions.
    """
    results = (
        session.query(db.BasicParameter, db.ComponentParameterDefinition)
        .join(
            db.ComponentParameterDefinition,
            db.BasicParameter.parameter_definition_id == db.ComponentParameterDefinition.id,
        )
        .filter(
            db.BasicParameter.component_instance_id == component_instance_id,
        )
        .all()
    )

    return [
        InstanceParameterWithDefinition(
            id=param_def.id,
            name=param_def.name,
            value=param.get_value(),
            type=param_def.type,
            nullable=param_def.nullable,
            default=param_def.default,
            ui_component=param_def.ui_component,
            ui_component_properties=param_def.ui_component_properties,
            is_advanced=param_def.is_advanced,
        )
        for param, param_def in results
    ]


def get_component_sub_components(
    session: Session,
    component_instance_id: UUID,
) -> list[db.ComponentSubInput]:
    """
    Retrieves the child component instances and their parameter definitions
    for a given parent component instance.
    """
    return (
        session.query(db.ComponentSubInput)
        .filter(
            db.ComponentSubInput.parent_component_instance_id == component_instance_id,
        )
        .all()
    )


def get_tool_description(
    session: Session,
    component_instance_id: UUID,
) -> Optional[db.ToolDescription]:
    """
    Retrieves the tool description associated with a specific component instance.
    """
    return (
        session.query(db.ToolDescription)
        .join(
            db.ComponentInstance,
            db.ComponentInstance.tool_description_id == db.ToolDescription.id,
        )
        .filter(db.ComponentInstance.id == component_instance_id)
        .first()
    )


def get_tool_description_component(
    session: Session,
    component_id: UUID,
) -> Optional[db.ToolDescription]:
    """
    Retrieves the tool description associated with a specific component.
    """
    return (
        session.query(db.ToolDescription)
        .join(
            db.Component,
            db.Component.default_tool_description_id == db.ToolDescription.id,
        )
        .filter(db.Component.id == component_id)
        .first()
    )


def get_tool_parameter_by_component_id(
    session: Session,
    component_id: UUID,
) -> Optional[db.Component]:
    """
    Retrieves the tool component associated with a specific component instance.
    """
    return (
        session.query(db.ComponentParameterDefinition)
        .filter(
            db.ComponentParameterDefinition.component_id == component_id,
            db.ComponentParameterDefinition.type == ParameterType.TOOL,
        )
        .first()
    )


def get_all_components_with_parameters(
    session: Session,
    allowed_stages: Optional[List[ReleaseStage]] = None,
) -> List[ComponentWithParametersDTO]:
    """
    Retrieves all components and their parameter definitions from the database.
    Component type parameters are moved to the tools list, while other parameters
    remain in the parameters list.

    Args:
        session (Session): SQLAlchemy session.
        allowed_stages (Optional[List[ReleaseStage]]): Optional release stage filter.

    Returns:
        List[ComponentWithParametersDTO]: A list of DTOs containing components,
        their tools (component parameters) and other parameter definitions.
    """
    if allowed_stages:

        components = session.query(db.Component).filter(db.Component.release_stage.in_(allowed_stages)).all()
    else:
        components = session.query(db.Component).all()

    # For each component, get its parameter definitions and build result
    result = []
    for component in components:
        try:
            parameters = get_component_parameter_definition_by_component_id(
                session,
                component.id,
            )

            subcomponent_params = get_subcomponent_param_def_by_component_id(
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
                            default=param.get_default(),
                            ui_component=param.ui_component,
                            ui_component_properties=param.ui_component_properties,
                            is_advanced=param.is_advanced,
                            order=param.order,
                        )
                    )

            default_tool_description_db = get_tool_description_component(session=session, component_id=component.id)
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
            if component.integration_id:
                integration = get_integration(session, component.integration_id)
            # Create ComponentWithParametersDTO
            result.append(
                ComponentWithParametersDTO(
                    id=component.id,
                    name=component.name,
                    description=component.description,
                    is_agent=component.is_agent,
                    integration=(
                        IntegrationSchema(
                            id=integration.id,
                            name=integration.name,
                            service=integration.service,
                        )
                        if component.integration_id
                        else None
                    ),
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
                    categories=get_categories(session, component.id),
                )
            )
        except Exception as e:
            LOGGER.error(f"Error getting component {component.name}: {e}")
    return result


def insert_component_parameter_definition(
    session: Session,
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
    Inserts a new component parameter definition into the database.
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
    session.commit()
    session.refresh(component_parameter_definition)
    return component_parameter_definition


def upsert_component_instance(
    session: Session,
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
    if not component_id:
        raise ValueError(
            "Impossible to create a component instance without a component",
        )

    component_instance = db.ComponentInstance(
        component_id=component_id,
        name=name,
        ref=ref,
        tool_description_id=tool_description_id,
        id=id_,
    )

    if id_ is None:
        session.add(component_instance)
    else:
        component_instance = session.merge(component_instance)

    session.commit()
    session.refresh(component_instance)
    return component_instance


def upsert_basic_parameter(
    session: Session,
    component_instance_id: UUID,
    parameter_definition_id: UUID,
    value: Optional[str] = None,
    order: Optional[int] = None,
    org_secret_id: Optional[UUID] = None,
) -> db.BasicParameter:
    """
    Inserts or updates a basic parameter. If a parameter with the same
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

    parameter = (
        session.query(db.BasicParameter)
        .filter(
            db.BasicParameter.component_instance_id == component_instance_id,
            db.BasicParameter.parameter_definition_id == parameter_definition_id,
            db.BasicParameter.order == order,
        )
        .first()
    )

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
    session.commit()
    session.refresh(parameter)
    return parameter


def upsert_sub_component_input(
    session: Session,
    parent_component_instance_id: UUID,
    child_component_instance_id: UUID,
    parameter_definition_id: UUID,
    order: Optional[int] = None,
) -> db.ComponentSubInput:
    """
    Upserts a sub-component input relationship into the database.
    If a relationship with the same parent, child, and parameter definition exists,
    it will be updated (PUT behavior).

    Args:
        session (Session): SQLAlchemy session.
        parent_component_instance_id (UUID): ID of the parent component instance.
        child_component_instance_id (UUID): ID of the child component instance.
        parameter_definition_id (UUID): ID of the parameter definition.
        order (Optional[int]): Optional order value.

    Returns:
        db.ComponentSubInput: The created or updated relationship object.
    """
    sub_input = (
        session.query(db.ComponentSubInput)
        .filter(
            db.ComponentSubInput.parent_component_instance_id == parent_component_instance_id,
            db.ComponentSubInput.child_component_instance_id == child_component_instance_id,
            db.ComponentSubInput.parameter_definition_id == parameter_definition_id,
        )
        .first()
    )

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

    session.commit()
    session.refresh(sub_input)
    return sub_input


def upsert_tool_description(
    session: Session,
    name: str,
    description: str,
    tool_properties: dict,
    required_tool_properties: list[str],
) -> db.ToolDescription:
    """
    Inserts or updates a tool description in the database.
    Uses name as unique identifier for upsert operation.
    Follows PUT semantics - completely replaces existing tool description.

    Returns:
        db.ToolDescription: The created or updated tool description object.
    """
    tool_description = (
        session.query(db.ToolDescription)
        .filter(
            db.ToolDescription.name == name,
        )
        .first()
    )

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

    session.commit()
    session.refresh(tool_description)
    return tool_description


# --- DELETE operations ---
def delete_component_instances(
    session: Session,
    component_instance_ids: list[UUID],
) -> None:
    """
    Deletes all component instances for a given component.
    Ensures cascading deletes on related entities.
    """

    query = session.query(db.ComponentInstance)
    if len(component_instance_ids) == 0:
        LOGGER.warning("No component instances to delete.")
        return
    if component_instance_ids:
        LOGGER.info(f"Deleting component instances with IDs: {component_instance_ids}")
        query = query.filter(db.ComponentInstance.id.in_(component_instance_ids))

    instances = query.all()
    for instance in instances:
        if get_component_instance_integration_relationship(session, instance.id):
            delete_linked_integration(session, instance.id)
        session.delete(instance)  # Triggers ORM cascade

    session.commit()


def delete_component_instance_parameters(
    session: Session,
    component_instance_id: UUID,
) -> None:
    """
    Deletes all parameters for a given component instance.
    """
    LOGGER.info(f"Deleting parameters for component instance {component_instance_id}")
    session.query(db.BasicParameter).filter(
        db.BasicParameter.component_instance_id == component_instance_id,
    ).delete()
    session.commit()
