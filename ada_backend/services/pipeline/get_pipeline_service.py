from logging import getLogger
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import ParameterType
from ada_backend.repositories.categories_repository import (
    fetch_associated_category_ids,
)
from ada_backend.repositories.component_repository import (
    get_component_by_id,
    get_component_instance_by_id,
    get_component_parameter_definition_by_component_version,
    get_component_sub_components,
    get_component_version_by_id,
    get_global_parameters_by_component_version_id,
    get_instance_parameters_with_definition,
    get_subcomponent_param_def_by_component_version,
    get_tool_parameter_by_component_version,
)
from ada_backend.repositories.integration_repository import (
    get_component_instance_integration_relationship,
    get_integration,
)
from ada_backend.repositories.tool_port_configuration_repository import get_tool_port_configurations
from ada_backend.schemas.components_schema import SubComponentParamSchema
from ada_backend.schemas.integration_schema import GraphIntegrationSchema
from ada_backend.schemas.parameter_schema import PipelineParameterReadSchema
from ada_backend.schemas.pipeline.base import ComponentRelationshipSchema, ToolDescriptionReadSchema
from ada_backend.schemas.pipeline.get_pipeline_schema import ComponentInstanceReadSchema
from ada_backend.schemas.pipeline.tool_port_configuration_schema import ToolPortConfigurationSchema
from ada_backend.services.tool_description_generator import (
    _get_tool_eligible_port_definitions,
    generate_tool_description,
)
from ada_backend.services.errors import ComponentInstanceNotFound, GraphValidationError
from ada_backend.utils.component_utils import get_ui_component_properties_with_llm_options

LOGGER = getLogger(__name__)


def _get_tool_description(session: Session, component_instance):
    """Build tool description dynamically from ToolPortConfiguration."""
    tool_description = generate_tool_description(session, component_instance)
    if not tool_description:
        return None
    return ToolDescriptionReadSchema(
        name=tool_description.name,
        description=tool_description.description,
        tool_properties=tool_description.tool_properties,
        required_tool_properties=tool_description.required_tool_properties,
    )


def _get_port_configurations(
    session: Session,
    component_instance_id: UUID,
    component_version_id: UUID,
) -> list[ToolPortConfigurationSchema]:
    """Return port configurations, filling defaults from PortDefinitions.

    Saved ToolPortConfiguration rows take precedence. For any tool-eligible
    port that has no explicit config, a default entry (setup_mode=ai_filled)
    is generated from the PortDefinition so the frontend always sees the
    full list.
    """
    configs = get_tool_port_configurations(
        session, component_instance_id, eager_load_input_port_instance=True, eager_load_port_definition=True
    )
    covered_port_def_ids = {c.port_definition_id for c in configs if c.port_definition_id}

    result = [
        ToolPortConfigurationSchema(
            id=config.id,
            component_instance_id=config.component_instance_id,
            input_port_instance_id=config.input_port_instance_id,
            parameter_id=config.port_definition_id,
            setup_mode=config.setup_mode,
            field_expression_id=(
                config.input_port_instance.field_expression_id if config.input_port_instance else None
            ),
            ai_name_override=config.ai_name_override,
            ai_description_override=config.ai_description_override,
            is_required_override=config.is_required_override,
            custom_parameter_type=config.custom_parameter_type,
            json_schema_override=(
                config.json_schema_override
                or (config.port_definition.default_tool_json_schema if config.port_definition else None)
            ),
            expression_json=config.expression_json,
            custom_ui_component_properties=config.custom_ui_component_properties,
        )
        for config in configs
    ]

    for port_definition in _get_tool_eligible_port_definitions(session, component_version_id):
        if port_definition.id not in covered_port_def_ids:
            result.append(
                ToolPortConfigurationSchema(
                    component_instance_id=component_instance_id,
                    parameter_id=port_definition.id,
                    json_schema_override=port_definition.default_tool_json_schema,
                )
            )

    return result


def get_component_instance(
    session: Session,
    component_instance_id: UUID,
    is_start_node: bool = False,
) -> ComponentInstanceReadSchema:
    """Get a component instance by ID"""
    component_instance = get_component_instance_by_id(session, component_instance_id)
    if component_instance is None:
        raise ComponentInstanceNotFound(component_instance_id)

    tool_description = _get_tool_description(session, component_instance)
    port_configurations = _get_port_configurations(
        session, component_instance_id, component_instance.component_version_id
    )

    parameters = get_instance_parameters_with_definition(
        session,
        component_instance_id,
    )
    global_params = get_global_parameters_by_component_version_id(session, component_instance.component_version_id)
    component_parameters = get_component_parameter_definition_by_component_version(
        session,
        component_instance.component_version_id,
    )
    for parameter in component_parameters:
        if parameter.type not in [ParameterType.COMPONENT, ParameterType.TOOL] and parameter.name not in [
            p.name for p in parameters
        ]:
            if parameter.name in [p.parameter_definition.name for p in global_params]:
                continue
            parameters.append(
                PipelineParameterReadSchema(
                    id=parameter.id,
                    name=parameter.name,
                    type=parameter.type,
                    nullable=parameter.nullable,
                    default=parameter.default,
                    ui_component=parameter.ui_component,
                    ui_component_properties=(
                        get_ui_component_properties_with_llm_options(
                            session,
                            parameter.model_capabilities,
                            parameter.ui_component_properties,
                        )
                        if parameter.type == ParameterType.LLM_MODEL
                        else parameter.ui_component_properties
                    ),
                    is_advanced=parameter.is_advanced,
                    drives_output_schema=getattr(parameter, "drives_output_schema", False),
                )
            )

    component_version = get_component_version_by_id(
        session, component_version_id=component_instance.component_version_id
    )
    if component_version is None:
        raise GraphValidationError(f"Component version {component_instance.component_version_id} not found")
    subcomponent_params = get_subcomponent_param_def_by_component_version(
        session, component_instance.component_version_id
    )
    tool_parameter = get_tool_parameter_by_component_version(session, component_instance.component_version_id)

    if component_version.integration_id:
        component_instance_integration = get_component_instance_integration_relationship(
            session, component_instance.id
        )
        integration = get_integration(session, component_version.integration_id)

    component = get_component_by_id(session, component_version.component_id)

    return ComponentInstanceReadSchema(
        id=component_instance_id,
        name=component_instance.name,
        ref=component_instance.ref,
        is_start_node=is_start_node,
        component_id=component.id,
        component_version_id=component_instance.component_version_id,
        version_tag=component_version.version_tag,
        release_stage=component_version.release_stage,
        tool_description=tool_description,
        tool_description_override=component_instance.tool_description_override,
        component_name=component.name,
        tool_parameter_name=tool_parameter.name if tool_parameter else None,
        component_description=component_version.description,
        is_agent=component.is_agent,
        is_protected=component.is_protected,
        function_callable=component.function_callable,
        can_use_function_calling=component.can_use_function_calling,
        icon=component.icon,
        subcomponents_info=[
            SubComponentParamSchema(
                component_version_id=param_child_def.child_component_version_id,
                parameter_name=subcomponent_param.name,
                is_optional=subcomponent_param.nullable,
            )
            for subcomponent_param, param_child_def in subcomponent_params
        ],
        parameters=[
            PipelineParameterReadSchema(
                id=param.id,
                name=param.name,
                value=param.value,
                type=param.type,
                nullable=param.nullable,
                default=param.default,
                ui_component=param.ui_component,
                ui_component_properties=(
                    get_ui_component_properties_with_llm_options(
                        session,
                        getattr(param, "model_capabilities", None),
                        param.ui_component_properties,
                    )
                    if param.type == ParameterType.LLM_MODEL
                    else param.ui_component_properties
                ),
                is_advanced=param.is_advanced,
                drives_output_schema=getattr(param, "drives_output_schema", False),
            )
            for param in parameters
        ],
        integration=(
            GraphIntegrationSchema(
                id=component_version.integration_id,
                name=integration.name if integration else None,
                service=integration.service if integration else None,
                secret_id=(
                    component_instance_integration.secret_integration_id if component_instance_integration else None
                ),
            )
            if component_version.integration_id
            else None
        ),
        category_ids=fetch_associated_category_ids(session, component.id) if component else [],
        port_configurations=port_configurations,
    )


def get_relationships(
    session: Session,
    component_instance_id: UUID,
) -> list[ComponentRelationshipSchema]:
    """Get all relationships for a component instance, excluding pipelines"""
    subinputs = get_component_sub_components(session, component_instance_id)
    return [
        ComponentRelationshipSchema(
            parent_component_instance_id=subinput.parent_component_instance_id,
            child_component_instance_id=subinput.child_component_instance_id,
            parameter_name=subinput.parameter_definition.name,
            order=subinput.order,
        )
        for subinput in subinputs
    ]
