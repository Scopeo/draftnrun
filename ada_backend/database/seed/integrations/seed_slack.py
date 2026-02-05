from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.models import (
    Component,
    ComponentParameterDefinition,
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from engine.integrations.providers import OAuthProvider


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

    slack_sender_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("7263b707-51ca-4d64-abfd-6c0907b3e860"),
            component_version_id=slack_sender_version.id,
            name="oauth_connection_id",
            type=ParameterType.STRING,
            nullable=False,
            order=0,
            ui_component=UIComponent.OAUTH_CONNECTION,
            ui_component_properties=UIComponentProperties(
                label="Slack Connection",
                description="Select your authorized Slack workspace connection",
                provider=OAuthProvider.SLACK.value,
                icon="logos:slack-icon",
            ).model_dump(exclude_unset=True, exclude_none=True),
        )
    ]

    upsert_components_parameter_definitions(session, slack_sender_parameter_definitions)

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
