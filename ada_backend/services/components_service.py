import logging
from typing import Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import ReleaseStage
from ada_backend.repositories.component_repository import get_all_components_with_parameters
from ada_backend.schemas.components_schema import ComponentsResponse

LOGGER = logging.getLogger(__name__)


def get_all_components_endpoint(session: Session, release_stage: Optional[ReleaseStage]) -> ComponentsResponse:
    components = get_all_components_with_parameters(session, release_stage=release_stage)
    return ComponentsResponse(components=components)
