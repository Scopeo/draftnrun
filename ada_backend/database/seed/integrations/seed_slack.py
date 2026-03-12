from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.models import Component
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


def seed_slack_components(session: Session):
    slack_sender_component = Component(
        id=COMPONENT_UUIDS["slack_sender"],
        name="Slack Sender",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="logos:slack-icon",
    )
    upsert_components(session, [slack_sender_component])

    slack_sender_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["slack_sender"],
        component_id=COMPONENT_UUIDS["slack_sender"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Send messages to Slack channels using OAuth. Supports threads and markdown formatting.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["slack_sender_tool_description"],
    )
    upsert_component_versions(session, [slack_sender_version])

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=slack_sender_version.component_id,
        release_stage=slack_sender_version.release_stage,
        component_version_id=slack_sender_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=slack_sender_component.id,
        category_ids=[CATEGORY_UUIDS["messaging"], CATEGORY_UUIDS["integrations"]],
    )
