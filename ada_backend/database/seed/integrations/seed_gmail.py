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


def seed_gmail_components(session: Session):
    gmail_sender_component = Component(
        id=COMPONENT_UUIDS["gmail_sender"],
        name="Gmail Sender",
        description="A component to send emails using Gmail API.",
        is_agent=True,
        integration_id=INTEGRATION_UUIDS["gmail_sender"],
        function_callable=True,
        can_use_function_calling=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["gmail_sender_tool_description"],
    )
    upsert_components(session, [gmail_sender_component])

    gmail_sender_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("6a74e715-ea03-42d9-bc1d-a1e1450f1ff7"),
            component_id=gmail_sender_component.id,
            name="save_as_draft",
            type=ParameterType.BOOLEAN,
            nullable=False,
            default=True,
            ui_component=UIComponent.CHECKBOX,
            ui_component_properties=UIComponentProperties(
                label="Save as Draft",
                description="If checked, the email will be saved as a draft instead of being sent immediately.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        )
    ]

    upsert_components_parameter_definitions(session, gmail_sender_parameter_definitions)
