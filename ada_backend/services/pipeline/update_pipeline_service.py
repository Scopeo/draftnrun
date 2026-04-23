import json
from logging import getLogger
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB
from ada_backend.repositories.component_repository import (
    delete_component_instance_parameters,
    get_component_by_id,
    get_component_parameter_definition_by_component_version,
    upsert_basic_parameter,
    upsert_component_instance,
)
from ada_backend.repositories.integration_repository import (
    delete_linked_integration,
    upsert_component_instance_integration,
)
from ada_backend.repositories.organization_repository import get_organization_secrets_from_project_id
from ada_backend.repositories.port_definition_repository import get_port_definition_default
from ada_backend.repositories.tool_port_configuration_repository import (
    delete_tool_port_configurations_for_instance,
    upsert_tool_port_configuration,
)
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from engine.field_expressions.parser import parse_expression_flexible
from engine.field_expressions.serializer import to_json as expression_to_json
from engine.llm_services.utils import get_llm_provider_and_model

LOGGER = getLogger(__name__)


def _normalize_expression_json(raw: object) -> dict | None:
    """Convert a raw expression_json value to a proper AST dict.

    The frontend may send a raw scalar (e.g. ``"pablo@draftnrun.com"``) instead
    of the canonical ``{"type": "literal", "value": "..."}`` shape.  This
    normalizes any supported value into a serialized AST dict before storage.
    """
    if raw is None:
        return None
    if isinstance(raw, (str, dict, list)):
        return expression_to_json(parse_expression_flexible(raw))
    return {"type": "literal", "value": str(raw)}


def create_or_update_component_instance(
    session: Session,
    instance_data: ComponentInstanceSchema,
    project_id: UUID,
) -> UUID:
    """Creates or updates a component instance with its parameters"""
    component_instance = upsert_component_instance(
        session=session,
        component_version_id=instance_data.component_version_id,
        name=instance_data.name,
        ref=instance_data.ref,
        tool_description_override=instance_data.tool_description_override,
        id_=instance_data.id,
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

    component = get_component_by_id(session, instance_data.component_id)
    component_name = component.name

    # Delete existing parameters (full replacement)
    delete_component_instance_parameters(session, instance_id)

    # Get parameter definitions for validation
    param_definitions: dict[str, db.ComponentParameterDefinition] = {
        p.name: p
        for p in get_component_parameter_definition_by_component_version(
            session,
            component_version_id=instance_data.component_version_id,
        )
    }

    for param_name, param_def in param_definitions.items():
        if param_def.type == db.ParameterType.LLM_API_KEY:
            organization_secrets = get_organization_secrets_from_project_id(session, project_id)
            if not organization_secrets:
                LOGGER.info(
                    f"No organization secrets found for project '{project_id}'. "
                    "Skipping LLM API key parameter creation."
                )
                continue

            model_name = get_port_definition_default(
                session,
                instance_data.component_version_id,
                COMPLETION_MODEL_IN_DB,
            )
            if model_name is None:
                LOGGER.warning(
                    f"Could not resolve completion_model for component '{component_name}'. "
                    "Skipping LLM API key parameter creation."
                )
                continue
            provider, _ = get_llm_provider_and_model(model_name)
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

    # Create/update parameters
    for param in instance_data.parameters:
        if param.name not in param_definitions:
            raise ValueError(
                f"Parameter '{param.name=}' not found in component definitions for component '{component_name}'"
            )

        param_def = param_definitions[param.name]

        if param_def.type == db.ParameterType.DATA_SOURCE:
            if param.value is None or (isinstance(param.value, str) and param.value.lower() == "none"):
                LOGGER.warning(
                    f"Data source parameter is missing in component '{component_name}'. "
                    "The component will not work until a data source is configured."
                )
                continue

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
                order=param.display_order,
            )

        elif param_def.type != db.ParameterType.LLM_API_KEY:
            if param.value is None and not param_def.nullable:
                if param_def.default is not None:
                    upsert_basic_parameter(
                        session=session,
                        component_instance_id=instance_id,
                        parameter_definition_id=param_def.id,
                        value=param_def.default,
                        order=param.display_order,
                    )
                else:
                    raise ValueError(
                        f"Parameter '{param.name}' cannot be None in component '{component_name}' "
                        f"because it is not nullable."
                    )
            elif param.value is not None:
                upsert_basic_parameter(
                    session=session,
                    component_instance_id=instance_id,
                    parameter_definition_id=param_def.id,
                    value=(
                        json.dumps(param.value) if isinstance(param.value, (dict, list)) else str(param.value)
                    ),  # Convert to string for storage
                    order=param.display_order,
                )

    if instance_data.port_configurations is not None:
        delete_tool_port_configurations_for_instance(session, instance_id)
        for tool_port_config in instance_data.port_configurations:
            upsert_tool_port_configuration(
                session=session,
                component_instance_id=instance_id,
                setup_mode=tool_port_config.setup_mode,
                port_definition_id=tool_port_config.parameter_id,
                input_port_instance_id=tool_port_config.input_port_instance_id,
                ai_name_override=tool_port_config.ai_name_override,
                ai_description_override=tool_port_config.ai_description_override,
                is_required_override=tool_port_config.is_required_override,
                custom_parameter_type=tool_port_config.custom_parameter_type,
                json_schema_override=tool_port_config.json_schema_override,
                expression_json=_normalize_expression_json(tool_port_config.expression_json),
                custom_ui_component_properties=tool_port_config.custom_ui_component_properties,
                id_=tool_port_config.id,
            )

    return instance_id
