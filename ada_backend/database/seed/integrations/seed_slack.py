from uuid import UUID
from sqlalchemy.orm import Session

from ada_backend.database.models import (
    Component,
    ComponentParameterDefinition,
    UIComponent,
    UIComponentProperties,
    ParameterType,
)
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.integrations.seed_integration import INTEGRATION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database import models as db


def seed_slack_components(session: Session):
    slack_sender_component = Component(
        id=COMPONENT_UUIDS["slack_sender"],
        name="Slack Sender",
        description="A component to send messages to Slack channels using OAuth integration.",
        is_agent=False,
        integration_id=INTEGRATION_UUIDS["slack_sender"],  # Use proper integration
        function_callable=True,
        can_use_function_calling=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["slack_sender_tool_description"],
    )
    upsert_components(session, [slack_sender_component])

    slack_sender_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("8c96f937-fc25-54fb-ce3f-c3f3672f3ff9"),
            component_id=slack_sender_component.id,
            name="default_channel",
            type=ParameterType.STRING,
            nullable=True,
            default=None,
            ui_component=UIComponent.TEXTFIELD,
            ui_component_properties=UIComponentProperties(
                label="Default Channel",
                description="Default channel to send messages to (e.g., #general or channel_id)",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
    ]

    upsert_components_parameter_definitions(session, slack_sender_parameter_definitions)
