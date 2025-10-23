from typing import Optional, List
from uuid import UUID
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ParameterType, ReleaseStage, UIComponent, UIComponentProperties
from ada_backend.repositories.categories_repository import fetch_associated_category_names
from ada_backend.repositories.integration_repository import (
    delete_linked_integration,
    get_component_instance_integration_relationship,
    get_integration,
)
from ada_backend.schemas.components_schema import (
    ComponentWithParametersDTO,
    SubComponentParamSchema,
)
from ada_backend.schemas.integration_schema import IntegrationSchema
from ada_backend.schemas.parameter_schema import ComponentParamDefDTO
from ada_backend.database.models import ComponentGlobalParameter
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.schemas.pipeline.base import ToolDescriptionSchema

LOGGER = logging.getLogger(__name__)


def get_global_parameters_by_component_id(
    session: Session,
    component_id: UUID,
) -> list[ComponentGlobalParameter]:
    return session.query(ComponentGlobalParameter).filter(ComponentGlobalParameter.component_id == component_id).all()


def has_global_parameter(
    session: Session,
    component_id: UUID,
    parameter_definition_id: UUID,
) -> bool:
    return (
        session.query(ComponentGlobalParameter)
        .filter(
            ComponentGlobalParameter.component_id == component_id,
            ComponentGlobalParameter.parameter_definition_id == parameter_definition_id,
        )
        .first()
        is not None
    )


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


@dataclass
class ComponentWithVersionDTO:
    id: UUID
    name: str
    description: Optional[str]
    version_id: UUID
    version_tag: str
    release_stage: ReleaseStage
    is_agent: bool
    function_callable: Optional[str]
    can_use_function_calling: bool
    is_protected: bool
    integration_id: Optional[UUID]
    default_tool_description_id: Optional[UUID] = None


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


def get_component_parameter_definition_by_component_version(
    session: Session,
    component_version_id: UUID,
    name: str,
) -> Optional[db.Component]:
    return (
        session.query(db.ComponentParameterDefinition)
        .filter(
            db.ComponentParameterDefinition.component_version_id == component_version_id,
        )
        .all()
    )


def delete_component_global_parameters(
    session: Session,
    component_id: UUID,
) -> None:
    session.query(ComponentGlobalParameter).filter(ComponentGlobalParameter.component_id == component_id).delete()
    session.commit()


def delete_component_by_id(
    session: Session,
    component_id: UUID,
) -> bool:
    """
    Deletes a component definition and associated global parameters.
    Returns True if deleted, False if not found.
    """
    component = get_component_by_id(session, component_id)
    if not component:
        return False

    instance_ids: List[UUID] = [
        ci.id
        for ci in session.query(db.ComponentInstance).filter(db.ComponentInstance.component_id == component_id).all()
    ]
    if instance_ids:
        delete_component_instances(session, component_instance_ids=instance_ids)

    # Delete parameter child relationships and definitions before removing component
    definition_ids: List[UUID] = [
        d.id
        for d in (
            session.query(db.ComponentParameterDefinition)
            .filter(
                db.ComponentParameterDefinition.component_id == component_id,
            )
            .all()
        )
    ]
    if definition_ids:
        (
            session.query(db.ComponentParameterChildRelationship)
            .filter(
                db.ComponentParameterChildRelationship.component_parameter_definition_id.in_(definition_ids),
            )
            .delete(synchronize_session=False)
        )

    (
        session.query(db.ComponentParameterDefinition)
        .filter(
            db.ComponentParameterDefinition.component_id == component_id,
        )
        .delete(synchronize_session=False)
    )

    # Remove category links
    (
        session.query(db.ComponentCategory)
        .filter(db.ComponentCategory.component_id == component_id)
        .delete(synchronize_session=False)
    )

    delete_component_global_parameters(session, component_id)

    session.delete(component)
    session.commit()
    return True


def get_subcomponent_param_def_by_component_version(
    session: Session,
    component_version_id: UUID,
) -> list[tuple[db.ComponentParameterDefinition, db.ComponentParameterChildRelationship]]:
    return (
        session.query(db.ComponentParameterDefinition, db.ComponentParameterChildRelationship)
        .join(
            db.ComponentParameterChildRelationship,
            db.ComponentParameterChildRelationship.component_parameter_definition_id
            == db.ComponentParameterDefinition.id,
        )
        .filter(
            db.ComponentParameterDefinition.component_version_id == component_version_id,
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


def get_component_instances_by_ids(
    session: Session,
    component_instance_ids: list[UUID],
) -> dict[UUID, db.ComponentInstance]:
    if not component_instance_ids:
        return {}
    rows = session.query(db.ComponentInstance).filter(db.ComponentInstance.id.in_(component_instance_ids)).all()
    return {row.id: row for row in rows}


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
        if param_def.type not in [db.ParameterType.LLM_API_KEY]  # Hide sensitive parameter types
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
    component_version_id: UUID,
) -> Optional[db.ToolDescription]:
    """
    Retrieves the tool description associated with a specific component version id.
    """
    return (
        session.query(db.ToolDescription)
        .join(
            db.ComponentVersion,
            db.ComponentVersion.default_tool_description_id == db.ToolDescription.id,
        )
        .filter(db.ComponentVersion.id == component_version_id)
        .first()
    )


def is_tool_description_used_by_multiple_instances(
    session: Session,
    tool_description_id: UUID,
) -> bool:
    """
    Checks if a tool description is used by multiple component instances.
    Returns True if used by more than one instance, False otherwise.
    """
    count = (
        session.query(db.ComponentInstance)
        .filter(db.ComponentInstance.tool_description_id == tool_description_id)
        .count()
    )
    return count > 1


def is_tool_description_default_for_component(
    session: Session,
    tool_description_id: UUID,
) -> bool:
    """
    Checks if a tool description is used as a default tool description for any component.
    Returns True if it's a default tool description, False otherwise.
    """
    count = session.query(db.Component).filter(db.Component.default_tool_description_id == tool_description_id).count()
    return count > 0


def get_tool_parameter_by_component_version(
    session: Session,
    component_version_id: UUID,
) -> Optional[db.ComponentParameterDefinition]:
    """
    Retrieves the tool component associated with a specific component instance.
    """
    return (
        session.query(db.ComponentParameterDefinition)
        .filter(
            db.ComponentParameterDefinition.component_version_id == component_version_id,
            db.ComponentParameterDefinition.type == ParameterType.TOOL,
        )
        .first()
    )


def get_current_component_versions(
    session: Session,
    allowed_stages: Optional[List[ReleaseStage]] = None,
) -> list[ComponentWithVersionDTO]:
    """
    Retrieves the current version of all components.
    """
    query = (
        session.query(db.Component, db.ComponentVersion)
        .join(db.Component, db.Component.id == db.ComponentVersion.component_id)
        .filter(db.ComponentVersion.is_current == True)
    )

    if allowed_stages:
        query = query.filter(db.ComponentVersion.release_stage.in_(allowed_stages))

    result = query.all()

    return [
        ComponentWithVersionDTO(
            id=comp.id,
            name=comp.name,
            description=ver.description,
            version_id=ver.id,
            version_tag=ver.version_tag,
            release_stage=ver.release_stage,
            is_agent=comp.is_agent,
            function_callable=comp.function_callable,
            can_use_function_calling=comp.can_use_function_calling,
            is_protected=comp.is_protected,
            integration_id=ver.integration_id,
            default_tool_description_id=ver.default_tool_description_id,
        )
        for comp, ver in result
    ]


# TODO: Put in service layer or write as query
def get_canonical_ports_for_components(
    session: Session, component_ids: list[UUID]
) -> dict[UUID, dict[str, Optional[str]]]:
    if not component_ids:
        return {}
    ports = session.query(db.PortDefinition).filter(db.PortDefinition.component_id.in_(component_ids)).all()
    result: dict[UUID, dict[str, Optional[str]]] = {}
    for p in ports:
        if p.is_canonical:
            entry = result.setdefault(p.component_id, {})
            if p.port_type == db.PortType.INPUT:
                entry["input"] = p.name
            elif p.port_type == db.PortType.OUTPUT:
                entry["output"] = p.name
    return result


def get_port_definitions_for_component_ids(
    session: Session,
    component_ids: list[UUID],
) -> list[db.PortDefinition]:
    if not component_ids:
        return []
    return session.query(db.PortDefinition).filter(db.PortDefinition.component_id.in_(component_ids)).all()


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
    components_with_version = get_current_component_versions(session, allowed_stages)

    # For each component, get its parameter definitions and build result
    result = []
    for component_with_version in components_with_version:
        try:
            parameters = get_component_parameter_definition_by_component_version(
                session,
                component_with_version.version_id,
            )

            # Hide parameters enforced globally for this component from the UI
            global_params = get_global_parameters_by_component_id(session, component.id)
            global_param_def_ids = {gp.parameter_definition_id for gp in global_params}

            subcomponent_params = get_subcomponent_param_def_by_component_version(
                session,
                component_with_version.version_id,
            )

            parameters_to_fill = []
            tool_param_name = None
            for param in parameters:
                if param.type == ParameterType.TOOL:
                    if tool_param_name is None:
                        tool_param_name = param.name
                    else:
                        raise ValueError(
                            f"Multiple tool parameters found for component {component_with_version.name}: "
                            f"{tool_param_name}, {param.name}"
                        )
                elif param.type != ParameterType.COMPONENT:
                    # Skip globally enforced parameters (they are not instance-editable)
                    if param.id in global_param_def_ids:
                        continue
                    parameters_to_fill.append(
                        ComponentParamDefDTO(
                            id=param.id,
                            component_version_id=param.component_version_id,
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

            default_tool_description_db = get_tool_description_component(
                session=session, component_id=component_with_version.version_id
            )
            tool_description = (
                ToolDescriptionSchema(
                    id=default_tool_description_db.id,
                    name=default_tool_description_db.name,
                    description=default_tool_description_db.description,
                    tool_properties=default_tool_description_db.tool_properties,
                    required_tool_properties=default_tool_description_db.required_tool_properties,
                ).model_dump()
                if default_tool_description_db
                else None
            )
            if component_with_version.integration_id:
                integration = get_integration(session, component_with_version.integration_id)
            # Create ComponentWithParametersDTO
            result.append(
                ComponentWithParametersDTO(
                    id=component_with_version.id,
                    name=component_with_version.name,
                    version_id=component_with_version.version_id,
                    version_tag=component_with_version.version_tag,
                    description=component_with_version.description,
                    is_agent=component_with_version.is_agent,
                    integration=(
                        IntegrationSchema(
                            id=integration.id,
                            name=integration.name,
                            service=integration.service,
                        )
                        if component_with_version.integration_id
                        else None
                    ),
                    tool_parameter_name=tool_param_name,
                    function_callable=component_with_version.function_callable,
                    release_stage=component_with_version.release_stage,
                    can_use_function_calling=component_with_version.can_use_function_calling,
                    tool_description=tool_description,
                    parameters=parameters_to_fill,
                    icon=component.icon,
                    subcomponents_info=[
                        SubComponentParamSchema(
                            version_id=param_child_def.child_component_version_id,
                            parameter_name=subcomponent_param.name,
                            is_optional=subcomponent_param.nullable,
                        )
                        for subcomponent_param, param_child_def in subcomponent_params
                    ],
                    categories=fetch_associated_category_names(session, component_with_version.id),
                )
            )
        except Exception as e:
            LOGGER.error(f"Error getting component {component_with_version.name}: {e}")
    return result


def insert_component_parameter_definition(
    session: Session,
    component_version_id: UUID,
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
        component_version_id=component_version_id,
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
    component_version_id: UUID,
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
    if not component_version_id:
        raise ValueError(
            "Impossible to create a component instance without a component version",
        )

    component_instance = db.ComponentInstance(
        component_version_id=component_version_id,
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
    # Prevent overriding global parameters
    parent_component_id = (
        session.query(db.ComponentInstance.component_id)
        .filter(db.ComponentInstance.id == component_instance_id)
        .scalar()
    )
    if parent_component_id and has_global_parameter(
        session,
        component_id=parent_component_id,
        parameter_definition_id=parameter_definition_id,
    ):
        raise ValueError("This parameter is enforced globally for the component and cannot be set per instance.")

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


def get_or_create_tool_description(
    session: Session,
    name: str,
    description: str,
    tool_properties: dict,
    required_tool_properties: list[str],
    id: Optional[UUID] = None,
) -> db.ToolDescription:
    # TODO: use id
    # First try to find by name and description only
    tool_description = (
        session.query(db.ToolDescription)
        .filter(
            db.ToolDescription.name == name,
            db.ToolDescription.description == description,
        )
        .first()
    )

    # TODO: remove when front sends id
    # If found, check if the JSON fields match
    if tool_description:
        # Compare the actual JSON values
        if (
            tool_description.tool_properties == tool_properties
            and tool_description.required_tool_properties == required_tool_properties
        ):
            return tool_description
        else:
            # JSON fields don't match, create a new one
            tool_description = None

    if not tool_description:
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
    Also deletes tool descriptions that are specific to these instances (not shared or default).
    """

    query = session.query(db.ComponentInstance)
    if len(component_instance_ids) == 0:
        LOGGER.warning("No component instances to delete.")
        return
    if component_instance_ids:
        LOGGER.info(f"Deleting component instances with IDs: {component_instance_ids}")
        query = query.filter(db.ComponentInstance.id.in_(component_instance_ids))

    instances = query.all()
    tool_descriptions_to_delete = []

    for instance in instances:
        if instance.tool_description_id:
            tool_description_id = instance.tool_description_id
            if not is_tool_description_used_by_multiple_instances(
                session, tool_description_id
            ) and not is_tool_description_default_for_component(session, tool_description_id):
                tool_descriptions_to_delete.append(tool_description_id)
                LOGGER.info(f"Marking tool description {tool_description_id} for deletion (instance-specific)")

        if get_component_instance_integration_relationship(session, instance.id):
            delete_linked_integration(session, instance.id)

        session.delete(instance)

    for tool_description_id in tool_descriptions_to_delete:
        tool_description = (
            session.query(db.ToolDescription).filter(db.ToolDescription.id == tool_description_id).first()
        )
        if tool_description:
            session.delete(tool_description)
            LOGGER.info(f"Deleted instance-specific tool description {tool_description_id}")

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


def upsert_specific_api_component_with_defaults(
    session: Session,
    tool_display_name: str,
    endpoint: str,
    method: str,
    headers_json: Optional[str],
    timeout_val: Optional[int],
    fixed_params_json: Optional[str],
) -> db.Component:
    """
    Ensure a specific API component exists with default parameter definitions.

    Returns the component.
    """
    component = get_component_by_name(session, tool_display_name)
    if not component:
        component = db.Component(
            name=tool_display_name,
            base_component="API Call",
            description=f"Preconfigured API tool for {tool_display_name}.",
            is_agent=False,
            function_callable=True,
            can_use_function_calling=False,
            release_stage=db.ReleaseStage.INTERNAL,
        )
        upsert_components(session, [component])

    param_defs = [
        db.ComponentParameterDefinition(
            component_id=component.id,
            name="endpoint",
            type=ParameterType.STRING,
            nullable=False,
            default=endpoint,
            ui_component=UIComponent.TEXTFIELD,
            ui_component_properties=UIComponentProperties(
                label="API Endpoint",
                placeholder="https://api.example.com/endpoint",
                description="The API endpoint URL to send requests to.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        db.ComponentParameterDefinition(
            component_id=component.id,
            name="method",
            type=ParameterType.STRING,
            nullable=False,
            default=method,
            ui_component=UIComponent.SELECT,
            ui_component_properties=UIComponentProperties(
                label="HTTP Method",
                options=[
                    {"label": "GET", "value": "GET"},
                    {"label": "POST", "value": "POST"},
                    {"label": "PUT", "value": "PUT"},
                    {"label": "DELETE", "value": "DELETE"},
                    {"label": "PATCH", "value": "PATCH"},
                ],
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        db.ComponentParameterDefinition(
            component_id=component.id,
            name="headers",
            type=ParameterType.JSON,
            nullable=True,
            default=headers_json,
            ui_component=UIComponent.TEXTAREA,
            ui_component_properties=UIComponentProperties(
                label="Headers",
                placeholder='{"Content-Type": "application/json"}',
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        db.ComponentParameterDefinition(
            component_id=component.id,
            name="timeout",
            type=ParameterType.INTEGER,
            nullable=True,
            default=str(timeout_val) if timeout_val is not None else None,
            ui_component=UIComponent.SLIDER,
            ui_component_properties=UIComponentProperties(
                label="Timeout (seconds)",
                min=1,
                max=120,
                step=1,
                placeholder="30",
            ).model_dump(exclude_unset=True, exclude_none=True),
            is_advanced=True,
        ),
        db.ComponentParameterDefinition(
            component_id=component.id,
            name="fixed_parameters",
            type=ParameterType.JSON,
            nullable=True,
            default=fixed_params_json,
            ui_component=UIComponent.TEXTAREA,
            ui_component_properties=UIComponentProperties(
                label="Fixed Parameters",
                placeholder='{"api_version": "v2", "format": "json"}',
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
    ]

    upsert_components_parameter_definitions(session, param_defs)
    return component


def set_component_default_tool_description(
    session: Session,
    component_id: UUID,
    tool_description_id: UUID,
) -> db.Component:
    component = get_component_by_id(session, component_id)
    if component is None:
        raise ValueError("Component not found when setting default tool description")
    component.default_tool_description_id = tool_description_id
    session.commit()
    session.refresh(component)
    return component


def insert_component_global_parameter(
    session: Session,
    component_id: UUID,
    parameter_definition_id: UUID,
    value: str,
) -> ComponentGlobalParameter:
    global_param = ComponentGlobalParameter(
        component_id=component_id,
        parameter_definition_id=parameter_definition_id,
        value=value,
    )
    session.add(global_param)
    session.commit()
    session.refresh(global_param)
    return global_param
