import logging
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.repositories.component_repository import (
    STAGE_HIERARCHY,
    count_component_instances,
    delete_component_by_id,
    get_all_components_with_parameters,
    get_component_by_id,
    get_port_definitions_for_component_version_ids,
)
from ada_backend.schemas.components_schema import ComponentsResponse, PortDefinitionSchema
from ada_backend.services.errors import EntityInUseDeletionError

LOGGER = logging.getLogger(__name__)


def get_all_components_endpoint(
    session: Session,
    release_stage: Optional[ReleaseStage],
) -> ComponentsResponse:
    if release_stage:
        allowed_stages = STAGE_HIERARCHY.get(release_stage, [release_stage])
    else:
        LOGGER.info("No release stage specified, retrieving all components.")
        allowed_stages = list(STAGE_HIERARCHY.keys())
    components = get_all_components_with_parameters(session, allowed_stages=allowed_stages)

    component_version_ids = [component.component_version_id for component in components]
    ports = get_port_definitions_for_component_version_ids(session, component_version_ids)
    comp_id_to_ports: dict[str, list[PortDefinitionSchema]] = {}
    for port in ports:
        comp_id_to_ports.setdefault(str(port.component_version_id), []).append(
            PortDefinitionSchema(
                name=port.name,
                port_type=port.port_type.value,
                is_canonical=port.is_canonical,
                is_optional=port.is_optional,
                description=port.description,
                ui_component=port.ui_component.value if port.ui_component else None,
                ui_component_properties=port.ui_component_properties,
            )
        )
    for component in components:
        component.port_definitions = comp_id_to_ports.get(str(component.component_version_id), [])

    return ComponentsResponse(components=components)


def delete_component_service(session: Session, component_id) -> None:
    component = get_component_by_id(session, component_id)
    if component:
        instance_count = count_component_instances(session, component_id)
        if instance_count > 0:
            raise EntityInUseDeletionError(component_id, instance_count, entity_type="component")
        delete_component_by_id(session, component_id)
