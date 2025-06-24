import json
from uuid import UUID
from logging import getLogger

from sqlalchemy.ext.asyncio import AsyncSession

from ada_backend.repositories.organization_repository import get_organization_secrets_from_project_id
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.database import models as db
from ada_backend.repositories.component_repository import (
    get_component_parameter_definition_by_component_id,
    upsert_component_instance,
    upsert_basic_parameter,
    upsert_tool_description,
    delete_component_instance_parameters,
)
from ada_backend.services.entity_factory import get_llm_provider_and_model
from ada_backend.services.registry import COMPLETION_MODEL_IN_DB

LOGGER = getLogger(__name__)


async def create_or_update_component_instance(
    session: AsyncSession,
    instance_data: ComponentInstanceSchema,
    project_id: UUID,
) -> UUID:
    """Creates or updates a component instance with its parameters asynchronously"""
    # Create tool description if needed
    tool_description = None
    if instance_data.tool_description:
        print("UPSERT DESCRIPTION")
        tool_description = await upsert_tool_description(
            session=session,
            name=instance_data.tool_description.name,
            description=instance_data.tool_description.description,
            tool_properties=instance_data.tool_description.tool_properties,
            required_tool_properties=instance_data.tool_description.required_tool_properties,
        )

    # Create/update instance (will create new if id is None, or upsert if id exists)
    print("UPSERT COMPONENT INSTANCE")
    component_instance = await upsert_component_instance(
        session=session,
        component_id=instance_data.component_id,
        name=instance_data.name,
        ref=instance_data.ref,
        tool_description_id=tool_description.id if tool_description else None,
        id_=instance_data.id,
    )
    instance_id = component_instance.id

    component_name = component_instance.component.name

    # Delete existing parameters (full replacement)
    print("DELETE COMPONENT INSTANCE PARAMETERS")
    await delete_component_instance_parameters(session, instance_id)

    # Get parameter definitions for validation
    LOGGER.info(f"Fetching parameter definitions for component '{component_name}' with ID {instance_data.component_id}")
    param_definitions: dict[str, db.ComponentParameterDefinition] = {
        p.name: p
        for p in await get_component_parameter_definition_by_component_id(
            session,
            instance_data.component_id,
        )
    }
    print("PARAMETER DEFINITIONS FETCHED")
    for param_name, param_def in param_definitions.items():
        if param_def.type == db.ParameterType.LLM_API_KEY:
            print("ORGANIZATION SECRETS")
            organization_secrets = await get_organization_secrets_from_project_id(session, project_id)
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
            await upsert_basic_parameter(
                session=session,
                component_instance_id=instance_id,
                parameter_definition_id=param_def.id,
                org_secret_id=param_secret.id,
                order=None,
            )
            LOGGER.info(f"LLM API key parameter '{param_name}' upsert for component '{component_name}' ")
    # Create/update parameters
    for param in instance_data.parameters:
        if param.name not in param_definitions:
            raise ValueError(
                f"Parameter '{param.name=}' not found in component definitions for component '{component_name}'"
            )

        param_def = param_definitions[param.name]

        if param_def.type == db.ParameterType.DATA_SOURCE:
            if param.value is None or (isinstance(param.value, str) and param.value.lower() == "none"):
                raise ValueError(f"Data source parameter cannot be None in component '{component_name}'")

        if param_def.type == db.ParameterType.SECRETS:
            organization_secrets = await get_organization_secrets_from_project_id(session, project_id)
            param_secret = None
            for secret in organization_secrets:
                if secret.key == param.name:
                    param_secret = secret
                    break
            if param_secret is None:
                raise ValueError(f"Secret '{param.name}' not found in organization secrets for project '{project_id}'")

            await upsert_basic_parameter(
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
                await upsert_basic_parameter(
                    session=session,
                    component_instance_id=instance_id,
                    parameter_definition_id=param_def.id,
                    value=(
                        json.dumps(param.value) if isinstance(param.value, dict) else str(param.value)
                    ),  # Convert to string for storage
                    order=param.order,
                )

    return instance_id