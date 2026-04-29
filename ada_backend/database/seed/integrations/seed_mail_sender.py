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

MAIL_SENDER_PARAMETER_GROUP_UUIDS: dict[str, UUID] = {
    "connection": UUID("1afcebb8-c315-4638-8717-959319efd81e"),
    "email_content": GMAIL_GROUP_EMAIL_CONTENT_ID,
    "recipients": GMAIL_GROUP_RECIPIENTS_ID,
    "attachments": GMAIL_GROUP_ATTACHMENTS_ID,
}


def seed_mail_sender_components(session: Session):
    mail_sender_component = Component(
        id=COMPONENT_UUIDS["mail_sender"],
        name="Mail Sender",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="tabler-mail",
    )
    upsert_components(session, [mail_sender_component])

    mail_sender_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["mail_sender"],
        component_id=COMPONENT_UUIDS["mail_sender"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Send email via Gmail or Outlook by connecting one provider.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["mail_sender_tool_description"],
    )
    upsert_component_versions(session, [mail_sender_version])

    mail_sender_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("90cedcdf-2bcb-4f12-a2c2-2fcaedd2b365"),
            component_version_id=mail_sender_version.id,
            name="gmail_oauth_connection_id",
            type=ParameterType.STRING,
            nullable=True,
            display_order=0,
            parameter_group_id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["connection"],
            parameter_order_within_group=0,
            ui_component=UIComponent.EXCLUSIVE_OAUTH_CONNECTION,
            ui_component_properties={
                "label": "Gmail Connection",
                "description": "Select a Gmail connection.",
                "provider": OAuthProvider.GMAIL.value,
                "icon": "logos-google-gmail",
            },
        ),
        ComponentParameterDefinition(
            id=UUID("eedfb8be-388e-444a-bebd-84599493661d"),
            component_version_id=mail_sender_version.id,
            name="outlook_oauth_connection_id",
            type=ParameterType.STRING,
            nullable=True,
            display_order=1,
            parameter_group_id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["connection"],
            parameter_order_within_group=1,
            ui_component=UIComponent.EXCLUSIVE_OAUTH_CONNECTION,
            ui_component_properties={
                "label": "Outlook Connection",
                "description": "Select an Outlook connection.",
                "provider": OAuthProvider.OUTLOOK.value,
                "icon": "custom-microsoft-outlook",
            },
        ),
        ComponentParameterDefinition(
            id=UUID("70a74f93-0756-45be-aea6-8de3216a28b6"),
            component_version_id=mail_sender_version.id,
            name="save_as_draft",
            type=ParameterType.BOOLEAN,
            nullable=False,
            default=True,
            ui_component=UIComponent.CHECKBOX,
            ui_component_properties=UIComponentProperties(
                type="checkbox",
                label="Save as Draft",
                description="If checked, the email will be saved as a draft instead of being sent immediately.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
    ]
    upsert_components_parameter_definitions(session, mail_sender_parameter_definitions)

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=mail_sender_version.component_id,
        release_stage=mail_sender_version.release_stage,
        component_version_id=mail_sender_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=mail_sender_component.id,
        category_ids=[CATEGORY_UUIDS["messaging"], CATEGORY_UUIDS["integrations"]],
    )


def seed_mail_sender_parameter_groups(session: Session):
    parameter_groups = [
        db.ParameterGroup(
            id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["connection"],
            name="Connection",
        ),
        db.ParameterGroup(
            id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["email_content"],
            name="Email Content",
        ),
        db.ParameterGroup(
            id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["recipients"],
            name="Recipients",
        ),
        db.ParameterGroup(
            id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["attachments"],
            name="Attachments",
        ),
    ]
    build_parameters_group(session, parameter_groups)


def seed_mail_sender_component_parameter_groups(session: Session):
    component_parameter_groups = [
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["mail_sender"],
            parameter_group_id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["connection"],
            group_order_within_component=0,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["mail_sender"],
            parameter_group_id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["email_content"],
            group_order_within_component=1,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["mail_sender"],
            parameter_group_id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["recipients"],
            group_order_within_component=2,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["mail_sender"],
            parameter_group_id=MAIL_SENDER_PARAMETER_GROUP_UUIDS["attachments"],
            group_order_within_component=3,
        ),
    ]
    build_parameters_group_definitions(session, component_parameter_groups)
