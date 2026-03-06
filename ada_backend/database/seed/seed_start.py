from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_versions,
    upsert_components,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


def seed_start_components(session: Session):
    start_component = db.Component(
        id=COMPONENT_UUIDS["start"],
        name="Start",
        is_agent=True,
        is_protected=True,
        icon="tabler-play",
    )
    upsert_components(
        session=session,
        components=[
            start_component,
        ],
    )
    start_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["start_v2"],
        component_id=COMPONENT_UUIDS["start"],
        version_tag="0.1.0",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Beginning of the workflow: setup the input format here.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[start_version],
    )

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=start_version.component_id,
        release_stage=start_version.release_stage,
        component_version_id=start_version.id,
    )
