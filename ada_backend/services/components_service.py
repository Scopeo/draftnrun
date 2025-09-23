import logging
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.repositories.component_repository import (
    get_all_components_with_parameters,
    get_component_by_id,
    delete_component_by_id,
)
from ada_backend.schemas.components_schema import ComponentsResponse
from ada_backend.services.errors import (
    ComponentNotFound,
    ProtectedComponentDeletionError,
)

LOGGER = logging.getLogger(__name__)

STAGE_HIERARCHY = {
    ReleaseStage.INTERNAL: [
        ReleaseStage.INTERNAL,
        ReleaseStage.EARLY_ACCESS,
        ReleaseStage.BETA,
        ReleaseStage.PUBLIC,
    ],
    ReleaseStage.BETA: [
        ReleaseStage.BETA,
        ReleaseStage.EARLY_ACCESS,
        ReleaseStage.PUBLIC,
    ],
    ReleaseStage.EARLY_ACCESS: [
        ReleaseStage.EARLY_ACCESS,
        ReleaseStage.PUBLIC,
    ],
    ReleaseStage.PUBLIC: [ReleaseStage.PUBLIC],
}


def get_all_components_endpoint(
    session: Session,
    release_stage: Optional[ReleaseStage],
) -> ComponentsResponse:
    if release_stage:
        allowed_stages = STAGE_HIERARCHY.get(release_stage, [release_stage])
    else:
        LOGGER.info("No release stage specified, retrieving all components.")
        allowed_stages = None
    components = get_all_components_with_parameters(
        session,
        allowed_stages=allowed_stages,
    )
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
    component.release_stage = release_stage
    session.add(component)
    session.commit()
