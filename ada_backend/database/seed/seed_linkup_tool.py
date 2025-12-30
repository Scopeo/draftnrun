from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_component_versions,
    upsert_release_stage_to_current_version_mapping,
    upsert_component_categories,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


def seed_linkup_tool_components(session: Session):
    linkup_tool = db.Component(
        id=COMPONENT_UUIDS["linkup_search_tool"],
        name="Internet Search (Linkup)",
        is_agent=True,
        function_callable=True,
        icon="tabler-world-search",
    )

    upsert_components(
        session=session,
        components=[
            linkup_tool,
        ],
    )
    linkup_tool_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["linkup_search_tool"],
        component_id=COMPONENT_UUIDS["linkup_search_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Linkup search tool for real-time web search and data connection",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["linkup_search_tool_description"],
    )
    upsert_component_versions(session, [linkup_tool_version])

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=linkup_tool_version.component_id,
        release_stage=linkup_tool_version.release_stage,
        component_version_id=linkup_tool_version.id,
    )
    upsert_component_categories(
        session=session,
        component_id=linkup_tool.id,
        category_ids=[CATEGORY_UUIDS["query"]],
    )
