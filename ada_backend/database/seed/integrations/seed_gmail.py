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
from ada_backend.database.seed.integrations.seed_integration import INTEGRATION_UUIDS
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    build_parameters_group,
    build_parameters_group_definitions,
)
from engine.integrations.gmail.gmail_sender import (
    GMAIL_GROUP_ATTACHMENTS_ID,
    GMAIL_GROUP_EMAIL_CONTENT_ID,
    GMAIL_GROUP_RECIPIENTS_ID,
)
from engine.integrations.providers import OAuthProvider

GMAIL_PARAMETER_GROUP_UUIDS: dict[str, UUID] = {
    "email_content": GMAIL_GROUP_EMAIL_CONTENT_ID,
    "recipients": GMAIL_GROUP_RECIPIENTS_ID,
    "attachments": GMAIL_GROUP_ATTACHMENTS_ID,
}


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

    gmail_sender_v2_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["gmail_sender_v2"],
        component_id=COMPONENT_UUIDS["gmail_sender"],
        version_tag="0.0.2",
        release_stage=db.ReleaseStage.INTERNAL,
        description="A component to send emails using Gmail API.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["gmail_sender_tool_description"],
    )
    upsert_component_versions(session, [gmail_sender_v2_version])

    gmail_sender_v2_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("c205b8b5-61aa-485b-af33-c9e7e67792db"),
            component_version_id=gmail_sender_v2_version.id,
            name="oauth_connection_id",
            type=ParameterType.STRING,
            nullable=True,
            display_order=0,
            parameter_order_within_group=0,
            ui_component=UIComponent.OAUTH_CONNECTION,
            ui_component_properties=UIComponentProperties(
                label="Gmail Connection",
                description="Select your authorized Gmail account connection",
                provider=OAuthProvider.GMAIL.value,
                icon="logos-google-gmail",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        ComponentParameterDefinition(
            id=UUID("9cbc77a8-cfd7-4f06-99f7-bf4d64849f6a"),
            component_version_id=gmail_sender_v2_version.id,
            name="save_as_draft",
            type=ParameterType.BOOLEAN,
            nullable=False,
            default=True,
            ui_component=UIComponent.CHECKBOX,
            ui_component_properties=UIComponentProperties(
                label="Save as Draft",
                description="If checked, the email will be saved as a draft instead of being sent immediately.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
    ]
    upsert_components_parameter_definitions(session, gmail_sender_v2_parameter_definitions)

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=gmail_sender_v2_version.component_id,
        release_stage=gmail_sender_v2_version.release_stage,
        component_version_id=gmail_sender_v2_version.id,
    )

    # v3: adds HTML email support
    gmail_sender_v3_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["gmail_sender_v3"],
        component_id=COMPONENT_UUIDS["gmail_sender"],
        version_tag="0.0.3",
        release_stage=db.ReleaseStage.INTERNAL,
        description="A component to send emails using Gmail API (with text or HTML).",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["gmail_sender_tool_description"],
    )
    upsert_component_versions(session, [gmail_sender_v3_version])

    gmail_sender_v3_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("4038cb41-b0cf-414d-9933-79d8090e4622"),
            component_version_id=gmail_sender_v3_version.id,
            name="oauth_connection_id",
            type=ParameterType.STRING,
            nullable=True,
            display_order=0,
            parameter_order_within_group=0,
            ui_component=UIComponent.OAUTH_CONNECTION,
            ui_component_properties=UIComponentProperties(
                label="Gmail Connection",
                description="Select your authorized Gmail account connection",
                provider=OAuthProvider.GMAIL.value,
                icon="logos-google-gmail",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        ComponentParameterDefinition(
            id=UUID("73f7de35-391e-4e73-8d30-2c238a4a3650"),
            component_version_id=gmail_sender_v3_version.id,
            name="save_as_draft",
            type=ParameterType.BOOLEAN,
            nullable=False,
            default=True,
            ui_component=UIComponent.CHECKBOX,
            ui_component_properties=UIComponentProperties(
                label="Save as Draft",
                description="If checked, the email will be saved as a draft instead of being sent immediately.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
    ]
    upsert_components_parameter_definitions(session, gmail_sender_v3_parameter_definitions)

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=gmail_sender_v3_version.component_id,
        release_stage=gmail_sender_v3_version.release_stage,
        component_version_id=gmail_sender_v3_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=gmail_sender_component.id,
        category_ids=[CATEGORY_UUIDS["messaging"], CATEGORY_UUIDS["integrations"]],
    )


def seed_gmail_parameter_groups(session: Session):
    """Seed parameter groups for Gmail Sender input ports."""

    parameter_groups = [
        db.ParameterGroup(
            id=GMAIL_PARAMETER_GROUP_UUIDS["email_content"],
            name="Email Content",
        ),
        db.ParameterGroup(
            id=GMAIL_PARAMETER_GROUP_UUIDS["recipients"],
            name="Recipients",
        ),
        db.ParameterGroup(
            id=GMAIL_PARAMETER_GROUP_UUIDS["attachments"],
            name="Attachments",
        ),
    ]
    build_parameters_group(session, parameter_groups)

    component_parameter_groups = [
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["gmail_sender_v3"],
            parameter_group_id=GMAIL_PARAMETER_GROUP_UUIDS["email_content"],
            group_order_within_component=1,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["gmail_sender_v3"],
            parameter_group_id=GMAIL_PARAMETER_GROUP_UUIDS["recipients"],
            group_order_within_component=2,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["gmail_sender_v3"],
            parameter_group_id=GMAIL_PARAMETER_GROUP_UUIDS["attachments"],
            group_order_within_component=3,
        ),
    ]
    build_parameters_group_definitions(session, component_parameter_groups)
