from uuid import UUID
from logging import getLogger
from sqlalchemy.ext.asyncio import AsyncSession

from ada_backend.schemas.components_schema import SubComponentParamSchema
from ada_backend.schemas.parameter_schema import PipelineParameterReadSchema
from ada_backend.services.agent_builder_service import _get_tool_description
from ada_backend.repositories.component_repository import (
    get_component_by_id,
    get_component_instance_by_id,
    get_instance_parameters_with_definition,
    get_subcomponent_param_def_by_component_id,
    get_tool_parameter_by_component_id,
    get_component_sub_components,
)
from ada_backend.schemas.pipeline.base import ComponentRelationshipSchema
from ada_backend.schemas.pipeline.get_pipeline_schema import ComponentInstanceReadSchema

LOGGER = getLogger(__name__)


async def get_component_instance(
    session: AsyncSession,
    component_instance_id: UUID,
    is_start_node: bool = False,
) -> ComponentInstanceReadSchema:
    """Get a component instance by ID asynchronously"""
    component_instance = await get_component_instance_by_id(session, component_instance_id)
    if component_instance is None:
        raise ValueError(f"Component instance {component_instance_id} not found")

    tool_description = await _get_tool_description(session, component_instance)

    parameters = await get_instance_parameters_with_definition(
        session,
        component_instance_id,
    )

    component = await get_component_by_id(session, component_id=component_instance.component_id)
    if component is None:
        raise ValueError(f"Component {component_instance.component_id} not found")
    subcomponent_params = await get_subcomponent_param_def_by_component_id(session, component_instance.component_id)
    tool_parameter = await get_tool_parameter_by_component_id(session, component_instance.component_id)

    return ComponentInstanceReadSchema(
        id=component_instance_id,
        name=component_instance.name,
        ref=component_instance.ref,
        is_start_node=is_start_node,
        component_id=component_instance.component_id,
        tool_description=tool_description,
        component_name=component.name,
        tool_parameter_name=tool_parameter.name if tool_parameter else None,
        component_description=component.description,
        is_agent=component.is_agent,
        is_protected=component.is_protected,
        function_callable=component.function_callable,
        can_use_function_calling=component.can_use_function_calling,
        subcomponents_info=[
            SubComponentParamSchema(
                id=param_child_def.child_component_id,
                parameter_name=subcomponent_param.name,
                is_optional=subcomponent_param.nullable,
            )
            for subcomponent_param, param_child_def in subcomponent_params
        ],
        parameters=[
            PipelineParameterReadSchema(
                name=param.name,
                value=param.value,
                type=param.type,
                nullable=param.nullable,
                default=param.default,
                ui_component=param.ui_component,
                ui_component_properties=param.ui_component_properties,
                is_advanced=param.is_advanced,
            )
            for param in parameters
        ],
    )


async def get_relationships(
    session: AsyncSession,
    component_instance_id: UUID,
) -> list[ComponentRelationshipSchema]:
    """Get all relationships for a component instance, excluding pipelines asynchronously"""
    subinputs = await get_component_sub_components(session, component_instance_id)
    return [
        ComponentRelationshipSchema(
            parent_component_instance_id=subinput.parent_component_instance_id,
            child_component_instance_id=subinput.child_component_instance_id,
            parameter_name=subinput.parameter_definition.name,
            order=subinput.order,
        )
        for subinput in subinputs
    ]