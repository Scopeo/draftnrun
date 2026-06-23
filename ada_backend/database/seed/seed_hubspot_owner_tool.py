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


def seed_hubspot_owner_components(session: Session):
    hubspot_owner_component = Component(
        id=COMPONENT_UUIDS["hubspot_owner_tool"],
        name="HubSpot Owner",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="logos:hubspot",
    )
    upsert_components(session, [hubspot_owner_component])

    hubspot_owner_component_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["hubspot_owner_tool"],
        component_id=COMPONENT_UUIDS["hubspot_owner_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Get HubSpot owner information by owner ID with owner fields available as root outputs.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["hubspot_owner_tool_description"],
    )
    upsert_component_versions(session, [hubspot_owner_component_version])

    hubspot_owner_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("cdde6f70-3904-45c5-ac39-f65bbf5db2e7"),
            component_version_id=hubspot_owner_component_version.id,
            name="method",
            type=ParameterType.STRING,
            nullable=False,
            default="GET",
            ui_component=UIComponent.SELECT,
            ui_component_properties=UIComponentProperties(
                label="HTTP Method",
                options=[{"label": "GET", "value": "GET"}],
            ).model_dump(exclude_unset=True, exclude_none=True),
            is_advanced=True,
        ),
        ComponentParameterDefinition(
            id=UUID("0f0758f6-5802-4092-92e0-5e837b139d9a"),
            component_version_id=hubspot_owner_component_version.id,
            name="timeout",
            type=ParameterType.INTEGER,
            default=30,
            ui_component=UIComponent.SLIDER,
            ui_component_properties=UIComponentProperties(
                label="Timeout (seconds)",
                min=1,
                max=120,
                step=1,
                placeholder="30",
            ).model_dump(exclude_unset=True, exclude_none=True),
            is_advanced=True,
        ),
    ]
    upsert_components_parameter_definitions(session, hubspot_owner_parameter_definitions)

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=hubspot_owner_component_version.component_id,
        release_stage=hubspot_owner_component_version.release_stage,
        component_version_id=hubspot_owner_component_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=hubspot_owner_component.id,
        category_ids=[CATEGORY_UUIDS["integrations"], CATEGORY_UUIDS["information_retrieval"]],
    )
