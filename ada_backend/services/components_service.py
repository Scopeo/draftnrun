import logging
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import ParameterType, PortType, ReleaseStage
from ada_backend.repositories.categories_repository import get_all_categories
from ada_backend.repositories.component_repository import (
    count_component_instances,
    delete_component_by_id,
    get_all_component_versions,
    get_component_by_id,
    get_current_component_versions,
    get_port_definitions_for_component_version_ids,
    process_components_with_versions,
)
from ada_backend.repositories.release_stage_repository import _STAGE_ORDER, STAGE_HIERARCHY
from ada_backend.schemas.category_schema import CategoryResponse
from ada_backend.schemas.components_schema import ComponentsResponse, PortDefinitionSchema
from ada_backend.schemas.parameter_schema import ComponentParamDefDTO, ParameterKind
from ada_backend.services.errors import EntityInUseDeletionError
from ada_backend.services.parameter_synthesis_utils import filter_conflicting_parameters

LOGGER = logging.getLogger(__name__)


def _process_components_with_ports(
    session: Session,
    components: list,
) -> ComponentsResponse:
    component_version_ids = [component.component_version_id for component in components]
    ports = get_port_definitions_for_component_version_ids(session, component_version_ids)
    comp_id_to_ports: dict[str, list[PortDefinitionSchema]] = {}
    input_ports_by_component_version: dict = {}
    for port in ports:
        comp_id_to_ports.setdefault(str(port.component_version_id), []).append(
            PortDefinitionSchema(
                name=port.name,
                port_type=port.port_type.value,
                is_canonical=port.is_canonical,
                description=port.description,
            )
        )
        # Track input ports per component_version for input-parameter synthesis
        if port.port_type == PortType.INPUT:
            input_ports_by_component_version.setdefault(port.component_version_id, []).append(port)
    for component in components:
        component.port_definitions = comp_id_to_ports.get(str(component.component_version_id), [])

        input_ports = input_ports_by_component_version.get(component.component_version_id, [])

        # Hide config parameters whose names collide with enabled input ports
        component.parameters = filter_conflicting_parameters(component.parameters or [], input_ports)

        for input_port in input_ports:
            component.parameters.append(
                ComponentParamDefDTO(
                    id=input_port.id,
                    component_version_id=input_port.component_version_id,
                    name=input_port.name,
                    type=ParameterType.STRING,
                    nullable=True,
                    default=None,
                    ui_component=input_port.ui_component,
                    ui_component_properties=input_port.ui_component_properties,
                    is_advanced=False,
                    parameter_group_id=None,
                    parameter_order_within_group=None,
                    parameter_group_name=None,
                    kind=ParameterKind.INPUT,
                )
            )

        # TODO: Temporary patch to ensure 'messages' appears first. Clean later.
        component.parameters.sort(
            key=lambda p: (
                0 if p.name == "messages" else 1,
                p.order if p.order is not None else 999,
                p.name,
            )
        )

    categories = get_all_categories(session)
    categories_list = [
        CategoryResponse(
            id=cat.id,
            name=cat.name,
            description=cat.description,
            icon=cat.icon,
            display_order=cat.display_order,
        )
        for cat in categories
    ]

    return ComponentsResponse(components=components, categories=categories_list)


def _get_allowed_stages(release_stage: Optional[ReleaseStage]) -> list[ReleaseStage]:
    if release_stage:
        return STAGE_HIERARCHY.get(release_stage, [release_stage])
    else:
        LOGGER.info("No release stage specified, retrieving all components.")
        return list(STAGE_HIERARCHY.keys())


def get_all_components_endpoint(
    session: Session,
    release_stage: Optional[ReleaseStage],
) -> ComponentsResponse:
    """
    Retrieves all components (current versions only) with their parameters and ports.
    When a release_stage is specified, returns components with the lowest available stage
    from the allowed hierarchy. For example, if INTERNAL is specified:
    - Returns INTERNAL version if it exists
    - Falls back to BETA, EARLY_ACCESS, or PUBLIC if INTERNAL doesn't exist
    - Each component appears only once with the lowest available stage
    """
    allowed_stages = _get_allowed_stages(release_stage)
    components_with_version = get_current_component_versions(session, allowed_stages)

    component_dict = {}
    for comp in components_with_version:
        comp_id = comp.component_id
        if comp_id not in component_dict:
            component_dict[comp_id] = comp
        else:
            current_stage_index = _STAGE_ORDER.index(comp.release_stage)
            existing_stage_index = _STAGE_ORDER.index(component_dict[comp_id].release_stage)
            if current_stage_index < existing_stage_index:
                component_dict[comp_id] = comp

    unique_components = list(component_dict.values())
    components = process_components_with_versions(session, unique_components)
    return _process_components_with_ports(session, components)


def get_all_components_global_endpoint(
    session: Session,
    release_stage: Optional[ReleaseStage],
) -> ComponentsResponse:
    """
    Retrieves all components (all versions) with their parameters and ports.
    """
    allowed_stages = _get_allowed_stages(release_stage)
    components_with_version = get_all_component_versions(session, allowed_stages)
    components = process_components_with_versions(session, components_with_version)
    return _process_components_with_ports(session, components)


def delete_component_service(session: Session, component_id) -> None:
    component = get_component_by_id(session, component_id)
    if component:
        instance_count = count_component_instances(session, component_id)
        if instance_count > 0:
            raise EntityInUseDeletionError(component_id, instance_count, entity_type="component")
        delete_component_by_id(session, component_id)
