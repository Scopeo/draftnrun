from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
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
from ada_backend.database.seed.integrations.seed_integration import INTEGRATION_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


def seed_gmail_components(session: Session):
    gmail_sender_component = Component(
        id=COMPONENT_UUIDS["gmail_sender"],
        name="Gmail Sender",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="logos-google-gmail",
    )
    upsert_components(session, [gmail_sender_component])
    gmail_sender_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["gmail_sender"],
        component_id=COMPONENT_UUIDS["gmail_sender"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description="A component to send emails using Gmail API.",
        integration_id=INTEGRATION_UUIDS["gmail_sender"],
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["gmail_sender_tool_description"],
    )
    upsert_component_versions(session, [gmail_sender_version])

    gmail_sender_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("6a74e715-ea03-42d9-bc1d-a1e1450f1ff7"),
            component_version_id=gmail_sender_version.id,
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

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=gmail_sender_version.component_id,
        release_stage=gmail_sender_version.release_stage,
        component_version_id=gmail_sender_version.id,
    )
