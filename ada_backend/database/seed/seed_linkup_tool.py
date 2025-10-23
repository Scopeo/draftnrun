from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_component_categories,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS


def seed_linkup_tool_components(session: Session):
    linkup_tool = db.Component(
        id=COMPONENT_UUIDS["linkup_search_tool"],
        name="Linkup Search Tool",
        description="Linkup search tool for real-time web search and data connection",
        is_agent=False,
        function_callable=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["linkup_search_tool_description"],
        icon="tabler-world-search",
    )

    upsert_components(
        session=session,
        components=[
            linkup_tool,
        ],
    )
    upsert_component_categories(
        session=session,
        component_id=linkup_tool.id,
        category_ids=[CATEGORY_UUIDS["query"]],
    )
