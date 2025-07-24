import logging
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.repositories.component_repository import get_all_components_with_parameters
from ada_backend.schemas.components_schema import ComponentsResponse

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
    return ComponentsResponse(components=components)
