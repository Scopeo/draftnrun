import logging
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.repositories.component_repository import (
    get_all_components_with_parameters,
    get_port_definitions_for_component_ids,
)
from ada_backend.schemas.components_schema import ComponentsResponse, PortDefinitionSchema

LOGGER = logging.getLogger(__name__)

STAGE_HIERARCHY = {
    ReleaseStage.INTERNAL: [ReleaseStage.INTERNAL, ReleaseStage.EARLY_ACCESS, ReleaseStage.BETA, ReleaseStage.PUBLIC],
    ReleaseStage.BETA: [ReleaseStage.BETA, ReleaseStage.EARLY_ACCESS, ReleaseStage.PUBLIC],
    ReleaseStage.EARLY_ACCESS: [ReleaseStage.EARLY_ACCESS, ReleaseStage.PUBLIC],
    ReleaseStage.PUBLIC: [ReleaseStage.PUBLIC],
}


def get_all_components_endpoint(session: Session, release_stage: Optional[ReleaseStage]) -> ComponentsResponse:
    if release_stage:
        allowed_stages = STAGE_HIERARCHY.get(release_stage, [release_stage])
    else:
        LOGGER.info("No release stage specified, retrieving all components.")
        allowed_stages = None
    components = get_all_components_with_parameters(session, allowed_stages=allowed_stages)

    component_ids = [c.id for c in components]
    ports = get_port_definitions_for_component_ids(session, component_ids)
    comp_id_to_ports: dict[str, list[PortDefinitionSchema]] = {}
    for p in ports:
        comp_id_to_ports.setdefault(str(p.component_id), []).append(
            PortDefinitionSchema(
                name=p.name,
                port_type=p.port_type.value,
                is_canonical=p.is_canonical,
                description=p.description,
            )
        )
    for c in components:
        c.__dict__["port_definitions"] = comp_id_to_ports.get(str(c.id), [])

    return ComponentsResponse(components=components)
