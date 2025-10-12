import json
from uuid import UUID
from logging import getLogger

from sqlalchemy.orm import Session

from ada_backend.repositories.integration_repository import (
    delete_linked_integration,
    upsert_component_instance_integration,
)
from ada_backend.repositories.organization_repository import get_organization_secrets_from_project_id
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.database import models as db
from ada_backend.repositories.component_repository import (
    get_component_parameter_definition_by_component_id,
    get_port_definitions_for_component_ids,
    upsert_component_instance,
    upsert_basic_parameter,
    upsert_tool_description,
    delete_component_instance_parameters,
    insert_component_parameter_definition,
)
from ada_backend.services.entity_factory import get_llm_provider_and_model
from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB

LOGGER = getLogger(__name__)


def create_or_update_component_instance(
    session: Session,
    instance_data: ComponentInstanceSchema,
    project_id: UUID,
) -> UUID:
    """Creates or updates a component instance with its parameters"""
    # Create tool description if needed
    tool_description = None
    if instance_data.tool_description:
        tool_description = upsert_tool_description(
            session=session,
            name=instance_data.tool_description.name,
            description=instance_data.tool_description.description,
            tool_properties=instance_data.tool_description.tool_properties,
            required_tool_properties=instance_data.tool_description.required_tool_properties,
        )

    # Create/update instance (will create new if id is None, or upsert if id exists)
    component_instance = upsert_component_instance(
        session=session,
        component_id=instance_data.component_id,
        name=instance_data.name,
        ref=instance_data.ref,
        tool_description_id=tool_description.id if tool_description else None,
        id_=instance_data.id,  # Pass the ID if provided, None otherwise
    )
    instance_id = component_instance.id

    if instance_data.integration and instance_data.integration.secret_id:
        upsert_component_instance_integration(session, instance_id, instance_data.integration.secret_id)
    elif instance_data.integration:
        LOGGER.warning(
            f"Integration provided for component instance {instance_id} but no secret ID found. "
            "Deleting existing integration relationship."
        )
        delete_linked_integration(session, instance_id)

    component_name = component_instance.component.name

    # Delete existing parameters (full replacement)
    delete_component_instance_parameters(session, instance_id)

    # Get parameter definitions for validation
    param_definitions: dict[str, db.ComponentParameterDefinition] = {
        p.name: p
        for p in get_component_parameter_definition_by_component_id(
            session,
            instance_data.component_id,
        )
    }

    # Get port definitions to allow input ports as parameters (for hardcoded values/templates)
    port_definitions = get_port_definitions_for_component_ids(session, [instance_data.component_id])
    input_port_names = {p.name for p in port_definitions if p.port_type == db.PortType.INPUT}

    for param_name, param_def in param_definitions.items():
        if param_def.type == db.ParameterType.LLM_API_KEY:
            organization_secrets = get_organization_secrets_from_project_id(session, project_id)
            if not organization_secrets:
                LOGGER.info(
                    f"No organization secrets found for project '{project_id}'. "
                    "Skipping LLM API key parameter creation."
                )
                continue

            model_name_param = next((p for p in instance_data.parameters if p.name == COMPLETION_MODEL_IN_DB), None)
            if model_name_param is None:
                raise ValueError(
                    f"LLM Model name parameter not found in component definitions for component {component_name}"
                )
            provider, _ = get_llm_provider_and_model(model_name_param.value)
            param_secret = next((s for s in organization_secrets if s.key == f"{provider}_api_key"), None)
            if param_secret is None:
                LOGGER.info(
                    f"LLM API key secret '{provider}_api_key' not found in organization secrets "
                    f"for project '{project_id}'. "
                    "Skipping LLM API key parameter creation."
                )
                continue
            upsert_basic_parameter(
                session=session,
                component_instance_id=instance_id,
                parameter_definition_id=param_def.id,
                org_secret_id=param_secret.id,
                order=None,
            )
            LOGGER.info(f"LLM API key parameter '{param_name}' upsert for component '{component_name}' ")

    # Track which parameters were provided by the client
    provided_param_names = {p.name for p in instance_data.parameters}

    # Create parameters with default values for non-nullable params not provided by client
    for param_name, param_def in param_definitions.items():
        if param_name not in provided_param_names:
            # Skip LLM_API_KEY params as they're handled separately above
            if param_def.type == db.ParameterType.LLM_API_KEY:
                continue

            # If parameter is not nullable and not provided, use default value
            if not param_def.nullable and param_def.default is not None:
                LOGGER.info(
                    f"Parameter '{param_name}' not provided for component '{component_name}', " f"using default value"
                )
                upsert_basic_parameter(
                    session=session,
                    component_instance_id=instance_id,
                    parameter_definition_id=param_def.id,
                    value=param_def.default,
                    order=None,
                )

    # Create/update parameters
    for param in instance_data.parameters:
        # Allow parameters that match input port names (for hardcoded values/templates)
        if param.name not in param_definitions:
            if param.name in input_port_names:
                # This is an input port parameter - we need to create a synthetic parameter definition
                # for it so it can be stored in basic_parameters and picked up by the template system
                LOGGER.debug(
                    f"Parameter '{param.name}' matches input port name for component '{component_name}'. "
                    "Creating synthetic parameter definition for template storage."
                )

                # Check if a synthetic parameter definition already exists
                # Refresh param_definitions to check if it exists
                existing_defs = get_component_parameter_definition_by_component_id(session, instance_data.component_id)
                synthetic_def = next((d for d in existing_defs if d.name == param.name), None)

                if not synthetic_def:
                    # Create a synthetic parameter definition for this input port
                    synthetic_def = insert_component_parameter_definition(
                        session=session,
                        component_id=instance_data.component_id,
                        name=param.name,
                        param_type=db.ParameterType.STRING,
                        nullable=True,  # Input ports are optional when hardcoded
                        default=None,
                        ui_component=None,
                        ui_component_properties=None,
                        is_advanced=False,
                    )
                    LOGGER.info(
                        f"Created synthetic parameter definition for input port '{param.name}' "
                        f"on component '{component_name}'"
                    )

                # Add to param_definitions so it's processed below
                param_definitions[param.name] = synthetic_def

            else:
                raise ValueError(
                    f"Parameter '{param.name=}' not found in component definitions for component '{component_name}'"
                )

        param_def = param_definitions[param.name]

        if param_def.type == db.ParameterType.DATA_SOURCE:
            if param.value is None or (isinstance(param.value, str) and param.value.lower() == "none"):
                raise ValueError(f"Data source parameter cannot be None in component '{component_name}'")

        if param_def.type == db.ParameterType.SECRETS:
            organization_secrets = get_organization_secrets_from_project_id(session, project_id)
            param_secret = None
            for secret in organization_secrets:
                if secret.key == param.name:
                    param_secret = secret
                    break
            if param_secret is None:
                raise ValueError(f"Secret '{param.name}' not found in organization secrets for project '{project_id}'")

            upsert_basic_parameter(
                session=session,
                component_instance_id=instance_id,
                parameter_definition_id=param_def.id,
                org_secret_id=param_secret.id,
                order=param.order,
            )

        elif param_def.type != db.ParameterType.LLM_API_KEY:
            if param.value is None and not param_def.nullable:
                raise ValueError(
                    f"Parameter '{param.name}' cannot be None in component '{component_name}' "
                    f"because it is not nullable."
                )
            elif param.value is not None:
                stored_value = json.dumps(param.value) if isinstance(param.value, dict) else str(param.value)
                upsert_basic_parameter(
                    session=session,
                    component_instance_id=instance_id,
                    parameter_definition_id=param_def.id,
                    value=stored_value,  # Convert to string for storage
                    order=param.order,
                )

    return instance_id
