import json
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.seed.seed_input import INPUT_PAYLOAD_PARAMETER_NAME
from ada_backend.repositories.organization_repository import get_organization_secrets_from_project_id
from engine.agent.agent import ToolDescription
from ada_backend.database.models import ComponentInstance
from ada_backend.repositories.component_repository import (
    get_component_instance_by_id,
    get_component_basic_parameters,
    get_component_sub_components,
    get_tool_description,
    get_tool_description_component,
)
from ada_backend.services.registry import FACTORY_REGISTRY


LOGGER = logging.getLogger(__name__)


def get_component_params(
    session: Session,
    component_instance_id: UUID,
    project_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """
    Fetches and resolves all parameters for a given component instance.

    Args:
        session (Session): SQLAlchemy session.
        component_instance_id (UUID): ID of the component instance.
        project_id (Optional[UUID]): ID of the project for resolving secrets.

    Returns:
        dict[str, Any]: Parameters where:
            - Parameters with order=None are returned as single values
            - Parameters with order!=None are grouped in lists, ordered by the order field
    """
    params = {}
    ordered_params: dict[str, list[tuple[int, Any]]] = {}  # name -> [(order, value), ...]

    for param in get_component_basic_parameters(session, component_instance_id):
        param_name = param.parameter_definition.name

        if param.organization_secret_id:
            if not project_id:
                raise ValueError(
                    f"Cannot resolve organization secret for parameter '{param_name}' without organization ID.",
                )
            secrets = get_organization_secrets_from_project_id(session, project_id, key=param.organization_secret.key)
            if not secrets:
                raise ValueError(f"No organization secret found for key '{param.organization_secret.key}'.")
            if len(secrets) > 1:
                raise ValueError(
                    f"Multiple organization secrets found for key '{param.organization_secret.key}'.",
                )
            value = secrets[0].secret
        else:
            value = param.get_value()
            if value is None:
                LOGGER.debug(
                    f"Parameter '{param_name}' has no value and is not a project secret. Skipping.",
                )
                continue

        if param.order is not None:
            # Parameter is part of a list
            if param_name not in ordered_params:
                ordered_params[param_name] = []
            ordered_params[param_name].append((param.order, value))
        else:
            # Parameter is a singleton
            params[param_name] = value

    # Process ordered parameters
    for name, values in ordered_params.items():
        # Sort by order and extract just the values
        params[name] = [v for _, v in sorted(values, key=lambda x: x[0])]

    return params


def instantiate_component(
    session: Session,
    component_instance_id: UUID,
    project_id: Optional[UUID] = None,
) -> Any:
    """
    Instantiate a component, resolving its dependencies recursively.

    Args:
        session (Session): SQLAlchemy session.
        component_instance_id (UUID): ID of the component instance to instantiate.
        project_id (Optional[UUID]): ID of the project for resolving secrets.

    Returns:
        Any: Instantiated component object.
    """
    # Fetch the component instance
    component_instance = get_component_instance_by_id(session, component_instance_id)
    if not component_instance:
        raise ValueError(f"Component instance {component_instance_id} not found.")
    component_name = component_instance.component.name
    LOGGER.debug(f"Init instantiation for component: {component_name}\n")

    # Fetch basic parameters
    input_params: dict[str, Any] = get_component_params(
        session,
        component_instance_id,
        project_id=project_id,
    )
    LOGGER.debug(f"{input_params=}\n")

    # Resolve sub-components
    sub_components = get_component_sub_components(session, component_instance_id)

    grouped_sub_components: dict[str, list[tuple[int, Any]]] = {}  # name -> [(order, instance), ...]

    for sub_component in sub_components:
        param_name = sub_component.parameter_definition.name
        LOGGER.debug(f"Found sub-component: {param_name=}, {sub_component.child_component_instance.ref=}\n")
        try:
            instantiated_sub_component = instantiate_component(
                session,
                sub_component.child_component_instance.id,
                project_id=project_id,
            )
            LOGGER.debug(f"Instantiated sub-component: {instantiated_sub_component}\n")
            # Group sub-components by parameter name
            if param_name not in grouped_sub_components:
                grouped_sub_components[param_name] = []
            grouped_sub_components[param_name].append((sub_component.order, instantiated_sub_component))
        except Exception as e:
            raise ValueError(
                f"Failed to instantiate sub-component '{param_name}' "
                f"for component instance {component_instance.ref}: {e}"
                f"Input parameters: {input_params}\n"
                f"Grouped sub-components: {grouped_sub_components}"
            ) from e
    LOGGER.debug(f"Resolved sub-components: {grouped_sub_components}\n")
    # Merge grouped sub-components into input parameters
    for parameter_name, sub_component_list in grouped_sub_components.items():
        LOGGER.debug(f"Merging sub-components for parameter '{parameter_name}': {sub_component_list}\n")
        if not any(order is not None for order, _ in sub_component_list):
            # All sub-components have order=None, treat as singleton if only one
            if len(sub_component_list) == 1:
                input_params[parameter_name] = sub_component_list[0][1]  # Extract just the instance
            else:
                input_params[parameter_name] = [instance for _, instance in sub_component_list]
        else:
            # Some sub-components have order, sort by order
            input_params[parameter_name] = [
                instance for _, instance in sorted(sub_component_list, key=lambda x: x[0] or 0)
            ]
    LOGGER.debug(f"Merged input parameters: {input_params}\n")

    # Resolve tool description if required
    tool_description = _get_tool_description(session, component_instance)
    if tool_description:
        input_params["tool_description"] = tool_description
    LOGGER.debug(f"Tool description: {tool_description}\n")
    if component_instance.component.is_agent or component_instance.component.function_callable:
        input_params["component_instance_name"] = component_instance.name
    # Instantiate the component using its factory
    LOGGER.debug(f"Trying to create component: {component_name} with input params: {input_params}\n")
    try:
        return FACTORY_REGISTRY.create(
            entity_name=component_name,
            **input_params,
        )
    except Exception as e:
        raise ValueError(
            f"Failed to instantiate component '{component_name}' "
            f"with instance ID {component_instance.ref}: {e}\n"
            f"Input parameters: {input_params}"
        ) from e


def _get_tool_description(
    session: Session,
    component_instance: ComponentInstance,
) -> Optional[ToolDescription]:
    """
    Get the tool description for a component instance.

    Args:
        session (Session): SQLAlchemy session.
        component_instance (ComponentInstance): Component instance to get the tool description for.

    Returns:
        Any: Tool description for the component instance.
    """

    db_tool_description = get_tool_description(session, component_instance.id)
    if not db_tool_description:
        db_tool_description = get_tool_description_component(session, component_instance.component_id)

    if not db_tool_description:
        LOGGER.warning(f"Tool description not found for agent component instance {component_instance.id}.")
        return None

    return ToolDescription(
        name=db_tool_description.name.replace(" ", "_"),
        description=db_tool_description.description,
        tool_properties=db_tool_description.tool_properties,
        required_tool_properties=db_tool_description.required_tool_properties,
    )


def get_default_values_for_sandbox(session, input_component_instance: UUID, project_id: UUID, input_data: dict):
    input_params = get_component_params(
        session,
        input_component_instance,
        project_id=project_id,
    )
    input_data_schema = json.loads(input_params[INPUT_PAYLOAD_PARAMETER_NAME])
    for input_data_key in input_data_schema.keys():
        if input_data_key not in input_data:
            input_data[input_data_key] = input_data_schema[input_data_key]
            LOGGER.debug(f"Add default value for {input_data_key}")
    return input_data
