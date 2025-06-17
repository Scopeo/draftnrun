import logging

from sqlalchemy.orm import Session

from ada_backend.repositories.component_repository import get_all_components_with_parameters
from ada_backend.schemas.components_schema import ComponentsResponse

LOGGER = logging.getLogger(__name__)


def get_all_components_endpoint(session: Session) -> ComponentsResponse:
    components = get_all_components_with_parameters(session)
    return ComponentsResponse(components=components)
