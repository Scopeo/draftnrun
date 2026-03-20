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
from engine.integrations.outlook.outlook_sender import (
    OUTLOOK_GROUP_ATTACHMENTS_ID,
    OUTLOOK_GROUP_EMAIL_CONTENT_ID,
    OUTLOOK_GROUP_RECIPIENTS_ID,
)
from engine.integrations.providers import OAuthProvider

OUTLOOK_PARAMETER_GROUP_UUIDS: dict[str, UUID] = {
    "email_content": OUTLOOK_GROUP_EMAIL_CONTENT_ID,
    "recipients": OUTLOOK_GROUP_RECIPIENTS_ID,
    "attachments": OUTLOOK_GROUP_ATTACHMENTS_ID,
}


def seed_outlook_components(session: Session):
    outlook_sender_component = Component(
        id=COMPONENT_UUIDS["outlook_sender"],
        name="Outlook Sender",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="custom-microsoft-outlook",
    )
    upsert_components(session, [outlook_sender_component])

    outlook_sender_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["outlook_sender"],
        component_id=COMPONENT_UUIDS["outlook_sender"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description="A component to send emails using Microsoft Outlook via the Graph API.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["outlook_sender_tool_description"],
    )
    upsert_component_versions(session, [outlook_sender_version])

    outlook_sender_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("f2725cec-f658-40f8-96bf-adf9484f47cd"),
            component_version_id=outlook_sender_version.id,
            name="oauth_connection_id",
            type=ParameterType.STRING,
            nullable=True,
            order=0,
            parameter_order_within_group=0,
            ui_component=UIComponent.OAUTH_CONNECTION,
            ui_component_properties=UIComponentProperties(
                label="Outlook Connection",
                description="Select your authorized Microsoft Outlook account connection",
                provider=OAuthProvider.OUTLOOK.value,
                icon="logos-microsoft-outlook",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        ComponentParameterDefinition(
            id=UUID("36a9df00-3ac3-45cc-badb-a6211c5bc581"),
            component_version_id=outlook_sender_version.id,
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
    upsert_components_parameter_definitions(session, outlook_sender_parameter_definitions)

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=outlook_sender_version.component_id,
        release_stage=outlook_sender_version.release_stage,
        component_version_id=outlook_sender_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=outlook_sender_component.id,
        category_ids=[CATEGORY_UUIDS["messaging"], CATEGORY_UUIDS["integrations"]],
    )


def seed_outlook_parameter_groups(session: Session):
    """Seed parameter groups for Outlook Sender input ports."""

    parameter_groups = [
        db.ParameterGroup(
            id=OUTLOOK_PARAMETER_GROUP_UUIDS["email_content"],
            name="Email Content",
        ),
        db.ParameterGroup(
            id=OUTLOOK_PARAMETER_GROUP_UUIDS["recipients"],
            name="Recipients",
        ),
        db.ParameterGroup(
            id=OUTLOOK_PARAMETER_GROUP_UUIDS["attachments"],
            name="Attachments",
        ),
    ]
    build_parameters_group(session, parameter_groups)

    component_parameter_groups = [
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["outlook_sender"],
            parameter_group_id=OUTLOOK_PARAMETER_GROUP_UUIDS["email_content"],
            group_order_within_component=1,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["outlook_sender"],
            parameter_group_id=OUTLOOK_PARAMETER_GROUP_UUIDS["recipients"],
            group_order_within_component=2,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_VERSION_UUIDS["outlook_sender"],
            parameter_group_id=OUTLOOK_PARAMETER_GROUP_UUIDS["attachments"],
            group_order_within_component=3,
        ),
    ]
    build_parameters_group_definitions(session, component_parameter_groups)

    session.commit()
