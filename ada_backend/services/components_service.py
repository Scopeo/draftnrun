import logging
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.repositories.component_repository import (
    STAGE_HIERARCHY,
    count_component_instances,
    delete_component_by_id,
    get_all_component_versions,
    get_component_by_id,
    get_current_component_versions,
    get_port_definitions_for_component_version_ids,
    process_components_with_versions,
)
from ada_backend.schemas.components_schema import ComponentsResponse, PortDefinitionSchema
from ada_backend.services.errors import EntityInUseDeletionError

LOGGER = logging.getLogger(__name__)


def _process_components_with_ports(
    session: Session,
    components: list,
) -> ComponentsResponse:
    """
    Shared processing function that adds port definitions to components and returns ComponentsResponse.
    This function handles the common logic for processing components regardless of whether
    they are current versions or all versions.
    """
    component_version_ids = [component.component_version_id for component in components]
    ports = get_port_definitions_for_component_version_ids(session, component_version_ids)
    comp_id_to_ports: dict[str, list[PortDefinitionSchema]] = {}
    for port in ports:
        comp_id_to_ports.setdefault(str(port.component_version_id), []).append(
            PortDefinitionSchema(
                name=port.name,
                port_type=port.port_type.value,
                is_canonical=port.is_canonical,
                description=port.description,
            )
        )
    for component in components:
        component.port_definitions = comp_id_to_ports.get(str(component.component_version_id), [])

    return ComponentsResponse(components=components)


def _get_allowed_stages(release_stage: Optional[ReleaseStage]) -> list[ReleaseStage]:
    """
    Helper function to determine allowed stages based on release_stage parameter.
    """
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
    """
    allowed_stages = _get_allowed_stages(release_stage)
    components_with_version = get_current_component_versions(session, allowed_stages)
    components = process_components_with_versions(session, components_with_version)
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
