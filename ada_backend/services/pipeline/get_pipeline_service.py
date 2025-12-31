from logging import getLogger
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import ParameterType
from ada_backend.repositories.categories_repository import fetch_associated_category_names
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
from ada_backend.schemas.components_schema import SubComponentParamSchema
from ada_backend.schemas.integration_schema import GraphIntegrationSchema
from ada_backend.schemas.parameter_schema import PipelineParameterReadSchema
from ada_backend.schemas.pipeline.base import ComponentRelationshipSchema
from ada_backend.schemas.pipeline.get_pipeline_schema import ComponentInstanceReadSchema
from ada_backend.services.agent_builder_service import _get_tool_description
from ada_backend.utils.component_utils import get_ui_component_properties_with_llm_options

LOGGER = getLogger(__name__)


def get_component_instance(
    session: Session,
    component_instance_id: UUID,
    is_start_node: bool = False,
) -> ComponentInstanceReadSchema:
    """Get a component instance by ID"""
    component_instance = get_component_instance_by_id(session, component_instance_id)
    if component_instance is None:
        raise ValueError(f"Component instance {component_instance_id} not found")

    tool_description = _get_tool_description(session, component_instance)

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
                )
            )

    component_version = get_component_version_by_id(
        session, component_version_id=component_instance.component_version_id
    )
    if component_version is None:
        raise ValueError(f"Component version {component_instance.component_version_id} not found")
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
        categories=fetch_associated_category_names(session, component.id) if component else [],
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
