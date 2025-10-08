import logging
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.repositories.component_repository import (
    STAGE_HIERARCHY,
    delete_component_by_id,
    get_all_components_with_parameters,
    get_component_by_id,
    delete_component_by_id,
    get_port_definitions_for_component_ids,
)
from ada_backend.schemas.components_schema import ComponentsResponse, PortDefinitionSchema
from ada_backend.services.errors import (
    ComponentNotFound,
    ProtectedComponentDeletionError,
)

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

    component_ids = [component.id for component in components]
    ports = get_port_definitions_for_component_ids(session, component_ids)
    comp_id_to_ports: dict[str, list[PortDefinitionSchema]] = {}
    for port in ports:
        comp_id_to_ports.setdefault(str(port.component_id), []).append(
            PortDefinitionSchema(
                name=port.name,
                port_type=port.port_type.value,
                is_canonical=port.is_canonical,
                description=port.description,
            )
        )
    for component in components:
        component.port_definitions = comp_id_to_ports.get(str(component.id), [])

    return ComponentsResponse(components=components)


def delete_component_service(session: Session, component_id) -> None:
    component = get_component_by_id(session, component_id)
    if component is None:
        raise ComponentNotFound(component_id)
    if getattr(component, "is_protected", False):
        raise ProtectedComponentDeletionError(component_id)
    deleted = delete_component_by_id(session, component_id)
    if not deleted:
        raise ComponentNotFound(component_id)


def update_component_release_stage_service(
    session: Session,
    component_id,
    release_stage: ReleaseStage,
) -> None:
    component = get_component_by_id(session, component_id)
    if component is None:
        raise ComponentNotFound(component_id)
    session.add(component)
    session.commit()
