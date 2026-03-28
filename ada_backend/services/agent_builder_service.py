import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.context import set_current_project_id
from ada_backend.database.models import PortSetupMode
from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.repositories.component_repository import (
    get_base_component_from_version,
    get_component_basic_parameters,
    get_component_instance_by_id,
    get_component_name_from_instance,
    get_component_sub_components,
    get_global_parameters_by_component_version_id,
)
from ada_backend.repositories.input_port_instance_repository import get_input_port_instances_for_component_instance
from ada_backend.repositories.integration_repository import (
    get_component_instance_integration_relationship,
    get_integration_from_component,
)
from ada_backend.repositories.organization_repository import get_organization_secrets_from_project_id
from ada_backend.repositories.tool_port_configuration_repository import get_tool_port_configurations
from ada_backend.services.errors import MissingDataSourceError, MissingIntegrationError
from ada_backend.services.registry import FACTORY_REGISTRY
from ada_backend.services.tool_description_generator import generate_tool_description
from ada_backend.utils.secret_resolver import replace_secret_placeholders
from engine.components.component import Component as EngineComponent
from engine.components.errors import (
    KeyTypePromptTemplateError,
    MCPConnectionError,
    MissingKeyPromptTemplateError,
)
from engine.components.types import ComponentAttributes
from engine.field_expressions.ast import LiteralNode
from engine.field_expressions.errors import FieldExpressionError
from engine.field_expressions.serializer import from_json as expression_from_json
from engine.graph_runner.field_expression_management import evaluate_expression

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


def _resolve_literal_field_expressions(
    session: Session,
    component_instance_id: UUID,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return pre-configured field expression values for a sub-tool component instance.

    LiteralNode expressions are returned as-is. VarNode and JsonBuildNode expressions
    are evaluated using the resolved variables dict (which contains decrypted secrets).
    RefNode and ConcatNode expressions depend on runtime graph context and are skipped.

    Only ports whose ToolPortConfiguration setup_mode is USER_SET (or tool-eligible
    ports without an explicit config, which default to AI_FILLED and are therefore
    excluded) are included.  Ports with is_tool_input=False are always included as
    they are constructor configuration ports outside the tool interface.
    """
    input_port_instances = get_input_port_instances_for_component_instance(
        session, component_instance_id, eager_load_field_expression=True, eager_load_port_definition=True
    )

    configs = get_tool_port_configurations(session, component_instance_id, eager_load_port_definition=True)
    mode_by_port_def_id: dict[UUID, PortSetupMode] = {
        c.port_definition_id: c.setup_mode for c in configs if c.port_definition_id
    }

    resolved_values: dict[str, Any] = {}

    # 1. Resolve from InputPortInstance field expressions (definition-based ports)
    for ipi in input_port_instances:
        if not (ipi.field_expression and ipi.field_expression.expression_json):
            continue
        expr_ast = expression_from_json(ipi.field_expression.expression_json)
        if not isinstance(expr_ast, LiteralNode):
            continue

        if ipi.port_definition_id:
            port_def = ipi.port_definition
            if port_def and port_def.is_tool_input:
                mode = mode_by_port_def_id.get(ipi.port_definition_id, PortSetupMode.AI_FILLED)
                if mode != PortSetupMode.USER_SET:
                    continue

        resolved_values[ipi.name] = expr_ast.value

    # 2. Resolve from ToolPortConfiguration.expression_json (custom ports + overrides)
    for config in configs:
        if config.setup_mode != PortSetupMode.USER_SET:
            continue
        if not config.expression_json:
            continue

        port_name = None
        if config.ai_name_override:
            port_name = config.ai_name_override
        elif config.port_definition:
            port_name = config.port_definition.name

        if not port_name:
            continue

        expr_ast = expression_from_json(config.expression_json)
        if isinstance(expr_ast, LiteralNode):
            resolved_values[port_name] = expr_ast.value

        elif variables is not None:
            try:
                resolved_values[port_name] = evaluate_expression(expr_ast, port_name, tasks={}, variables=variables)
            except FieldExpressionError:
                pass
    return resolved_values


async def instantiate_component(
    session: Session,
    component_instance_id: UUID,
    project_id: Optional[UUID] = None,
    variables: dict[str, Any] | None = None,
) -> Any:
    """
    Instantiate a component, resolving its dependencies recursively.

    Args:
        session (Session): SQLAlchemy session.
        component_instance_id (UUID): ID of the component instance to instantiate.
        project_id (Optional[UUID]): ID of the project for resolving secrets.
        variables (dict | None): Resolved variables (including decrypted secrets) for evaluating
            non-literal field expressions on sub-tool inputs (e.g. json_build + VarNode).

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
            raise MissingIntegrationError(
                integration_name=component_integration.name,
                integration_service=component_integration.service,
                component_instance_name=component_instance.name,
            )

    # Resolve sub-components
    sub_components = get_component_sub_components(session, component_instance_id)

    grouped_sub_components: dict[str, list[tuple[int, Any]]] = {}  # name -> [(order, instance), ...]
    # Maps tool description names to their pre-configured literal run inputs.
    # Passed to AIAgent so _run_tool_call can merge them with LLM-provided arguments.
    tool_pre_configured_inputs: dict[str, dict[str, Any]] = {}

    for sub_component in sub_components:
        param_name = sub_component.parameter_definition.name
        LOGGER.debug(f"Found sub-component: {param_name=}, {sub_component.child_component_instance.ref=}\n")
        try:
            instantiated_sub_component = await instantiate_component(
                session,
                sub_component.child_component_instance.id,
                project_id=project_id,
                variables=variables,
            )
            LOGGER.debug(f"Instantiated sub-component: {instantiated_sub_component}\n")

            # Collect pre-configured field expression values for this tool and map them to their
            # tool description names so AIAgent can inject them at _run_tool_call time.
            # Variables are passed to also evaluate VarNode/JsonBuildNode expressions (e.g. secrets).
            pre_configured = _resolve_literal_field_expressions(
                session, sub_component.child_component_instance.id, variables=variables
            )
            if pre_configured:
                get_descriptions = getattr(instantiated_sub_component, "get_tool_descriptions", None)
                if get_descriptions:
                    for tool_description in get_descriptions():
                        tool_pre_configured_inputs[tool_description.name] = pre_configured

            # Group sub-components by parameter name
            if param_name not in grouped_sub_components:
                grouped_sub_components[param_name] = []
            grouped_sub_components[param_name].append((sub_component.order, instantiated_sub_component))
        except (
            MissingDataSourceError,
            MissingKeyPromptTemplateError,
            KeyTypePromptTemplateError,
            MCPConnectionError,
            MissingIntegrationError,
        ):
            raise
        except Exception as e:
            error_msg = (
                f"Failed to instantiate sub-component '{param_name}' "
                f"for component instance {component_instance.name} "
                f"({component_instance.id}): {e}\n"
            )
            LOGGER.error(
                error_msg,
                exc_info=True,
                extra={
                    "input_params": input_params,
                    "grouped_sub_components": grouped_sub_components,
                },
            )
            raise ValueError(error_msg) from e
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

    factory = FACTORY_REGISTRY.get(component_instance.component_version_id)
    entity_class = getattr(factory, "entity_class", None)
    if entity_class and issubclass(entity_class, EngineComponent):
        tool_description = generate_tool_description(session, component_instance)
        if tool_description:
            input_params["tool_description"] = tool_description
        LOGGER.debug(f"Tool description: {tool_description}\n")
    input_params["component_attributes"] = ComponentAttributes(
        component_instance_name=component_instance.name,
        component_instance_id=component_instance.id,
    )
    if tool_pre_configured_inputs:
        input_params["tool_pre_configured_inputs"] = tool_pre_configured_inputs
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
        set_current_project_id(project_id)
        return await FACTORY_REGISTRY.create(
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
        LOGGER.error(
            f"Failed to instantiate component '{component_name}' "
            f"with version ID {component_instance.component_version_id} "
            f"and instance ID {component_instance.id}: {e}. "
            f"Input parameters: {input_params}",
            exc_info=True,
        )
        raise ValueError(
            f"Failed to instantiate component '{component_name}' "
            f"with version ID {component_instance.component_version_id} "
            f"and instance ID {component_instance.id}: {e}"
        ) from e
