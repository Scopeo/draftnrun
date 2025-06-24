import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ada_backend.repositories.component_repository import get_all_components_with_parameters
from ada_backend.schemas.components_schema import ComponentsResponse

LOGGER = logging.getLogger(__name__)


async def get_all_components_endpoint(session: AsyncSession) -> ComponentsResponse:
    """"""
    components = await get_all_components_with_parameters(session)
    return ComponentsResponse(components=components)
