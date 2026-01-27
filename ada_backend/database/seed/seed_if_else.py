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


def seed_if_else_components(session: Session):
    if_else = db.Component(
        id=COMPONENT_UUIDS["if_else"],
        name="If/Else",
        is_agent=True,
        function_callable=False,
        is_protected=False,
        icon="tabler-git-branch",
    )
    upsert_components(
        session=session,
        components=[
            if_else,
        ],
    )
    if_else_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["if_else"],
        component_id=COMPONENT_UUIDS["if_else"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.BETA,
        description=(
            "A conditional component that controls workflow execution by evaluating multiple conditions "
            "with AND/OR logic. "
            "If the conditions evaluate to true, downstream nodes continue. If false, downstream execution is halted."
        ),
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[if_else_version],
    )

    # Note: Parameter definitions are now auto-seeded from the Pydantic schema
    # with json_schema_extra in engine/components/if_else.py

    upsert_component_categories(
        session=session,
        component_id=if_else.id,
        category_ids=[CATEGORY_UUIDS["workflow_logic"]],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=if_else.id,
        release_stage=if_else_version.release_stage,
        component_version_id=if_else_version.id,
    )
