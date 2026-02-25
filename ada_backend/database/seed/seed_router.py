from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
)


def seed_router_components(session: Session):
    router = db.Component(
        id=COMPONENT_UUIDS["router"],
        name="Router",
        is_agent=True,
        function_callable=False,
        is_protected=False,
        icon="tabler-arrows-split",
    )
    upsert_components(
        session=session,
        components=[
            router,
        ],
    )
    router_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["router"],
        component_id=COMPONENT_UUIDS["router"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.BETA,
        description=(
            "A routing component that directs data to multiple outputs based on equality conditions. "
            "Each route checks if the input value equals a specific condition. "
            "Matching routes continue execution while non-matching routes are halted. "
            "Similar to a switch/case statement."
        ),
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[router_version],
    )

    upsert_component_categories(
        session=session,
        component_id=router.id,
        category_ids=[CATEGORY_UUIDS["workflow_logic"]],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=router.id,
        release_stage=router_version.release_stage,
        component_version_id=router_version.id,
    )
