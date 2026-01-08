import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import ComponentInstance
from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.repositories.component_repository import (
    get_base_component_from_version,
    get_component_basic_parameters,
    get_component_instance_by_id,
    get_component_name_from_instance,
    get_component_sub_components,
    get_global_parameters_by_component_version_id,
    get_tool_description,
    get_tool_description_component,
)
from ada_backend.repositories.integration_repository import (
    get_component_instance_integration_relationship,
    get_integration_from_component,
)
from ada_backend.repositories.organization_repository import get_organization_secrets_from_project_id
from ada_backend.schemas.pipeline.base import ToolDescriptionSchema
from ada_backend.services.errors import MissingDataSourceError
from ada_backend.services.registry import FACTORY_REGISTRY
from ada_backend.utils.secret_resolver import replace_secret_placeholders
from engine.components.errors import (
    KeyTypePromptTemplateError,
    MCPConnectionError,
    MissingKeyPromptTemplateError,
)
from engine.components.types import ComponentAttributes, ToolDescription

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
    component_name = get_component_name_from_instance(session, component_instance_id)
    if not component_instance:
        raise ValueError(f"Component instance {component_instance_id} not found.")
    component_version_id = component_instance.component_version_id
    LOGGER.debug(f"Init instantiation for component {component_name} version: {component_version_id}\n")

    # Fetch basic parameters
    input_params: dict[str, Any] = get_component_params(
        session,
        component_instance_id,
        project_id=project_id,
    )
    LOGGER.debug(f"{input_params=}\n")

    component_integration = get_integration_from_component(session, component_instance.component_version_id)

    if component_integration:
        # If the component has an integration, we need to fetch the secret integration ID
        # from the component instance's integration relationship
        LOGGER.debug(f"Component {component_name} has an integration. Fetching integration relationship.\n")
        integration_relationship = get_component_instance_integration_relationship(
            session=session, component_instance_id=component_instance_id
        )
        if integration_relationship:
            input_params["secret_integration_id"] = integration_relationship.secret_integration_id
        else:
            raise ValueError(
                f"Please add integration {component_integration.name}:{component_integration.service} "
                f"for component instance {component_instance.name}"
            )

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
        except (
            MissingDataSourceError,
            MissingKeyPromptTemplateError,
            KeyTypePromptTemplateError,
            MCPConnectionError,
        ):
            raise
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

    # Apply global component parameters (non-overridable, invisible to UI)
    try:
        globals_ = get_global_parameters_by_component_version_id(
            session,
            component_instance.component_version_id,
        )
        grouped_globals: dict[str, list[tuple[int, Any]]] = {}
        for gparam in globals_:
            pname = gparam.parameter_definition.name
            if gparam.order is not None:
                if pname not in grouped_globals:
                    grouped_globals[pname] = []
                grouped_globals[pname].append((gparam.order, gparam.get_value()))
            else:
                # Scalar: enforce globally
                input_params[pname] = gparam.get_value()
        for pname, values in grouped_globals.items():
            input_params[pname] = [v for _, v in sorted(values, key=lambda x: x[0])]
        LOGGER.debug(f"Input parameters after applying global component parameters: {input_params}\n")
    except Exception as e:
        raise ValueError(
            f"Failed to apply global component parameters for instance {component_instance.ref}: {e}"
        ) from e

    # Resolve secret placeholders for any parameter in input_params.
    key_to_secret: dict[str, str] | None = None
    if project_id:
        secrets = get_organization_secrets_from_project_id(session, project_id)
        key_to_secret = {s.key: s.secret for s in secrets}

    input_params = replace_secret_placeholders(input_params, key_to_secret)

    # Resolve tool description if required
    tool_description_schema = _get_tool_description(session, component_instance)
    if tool_description_schema:
        input_params["tool_description"] = ToolDescription(
            name=tool_description_schema.name,
            description=tool_description_schema.description,
            tool_properties=tool_description_schema.tool_properties,
            required_tool_properties=tool_description_schema.required_tool_properties,
        )
    LOGGER.debug(f"Tool description: {tool_description_schema}\n")
    input_params["component_attributes"] = ComponentAttributes(
        component_instance_name=component_instance.name,
        component_instance_id=component_instance.id,
    )
    # Instantiate the component using its factory
    LOGGER.debug(
        f"Trying to create component: {component_name} "
        f"(version ID: {component_instance.component_version_id}) "
        f"with input params: {input_params}\n"
    )
    try:
        component_version_id = component_instance.component_version_id
        base_component = get_base_component_from_version(session, component_version_id)
        if base_component and base_component == "API Call":
            component_version_id = COMPONENT_VERSION_UUIDS["api_call_tool"]
        # Create component instance using the component version ID
        return FACTORY_REGISTRY.create(
            component_version_id=component_version_id,
            **input_params,
        )
    except ConnectionError as e:
        raise ConnectionError(
            f"Failed to connect to database for component '{component_name}' "
            f"(instance ID: {component_instance.id}): {str(e)}"
        ) from e
    except (MissingDataSourceError, MCPConnectionError):
        raise
    except Exception as e:
        raise ValueError(
            f"Failed to instantiate component '{component_name}' "
            f"with version ID {component_instance.component_version_id} "
            f"and instance ID {component_instance.id}: {e}\n"
            f"Input parameters: {input_params}"
        ) from e


def _get_tool_description(
    session: Session,
    component_instance: ComponentInstance,
) -> Optional[ToolDescriptionSchema]:
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
        db_tool_description = get_tool_description_component(session, component_instance.component_version_id)

    if not db_tool_description:
        LOGGER.warning(f"Tool description not found for agent component instance {component_instance.id}.")
        return None

    return ToolDescriptionSchema(
        id=db_tool_description.id,
        name=db_tool_description.name.replace(" ", "_"),
        description=db_tool_description.description,
        tool_properties=db_tool_description.tool_properties,
        required_tool_properties=db_tool_description.required_tool_properties,
    )
