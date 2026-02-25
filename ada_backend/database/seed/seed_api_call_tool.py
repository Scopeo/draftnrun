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


def seed_api_call_components(session: Session):
    api_call_component = Component(
        id=COMPONENT_UUIDS["api_call_tool"],
        name="API Call",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="tabler-api",
    )
    upsert_components(session, [api_call_component])

    api_call_component_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["api_call_tool"],
        component_id=COMPONENT_UUIDS["api_call_tool"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="A generic API tool that can make HTTP requests to any API endpoint.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_api_call_tool_description"],
    )
    upsert_component_versions(session, [api_call_component_version])

    api_call_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("c3d4e5f6-a7b8-9012-cdef-123456789012"),
            component_version_id=api_call_component_version.id,
            name="method",
            type=ParameterType.STRING,
            nullable=False,
            ui_component=UIComponent.SELECT,
            ui_component_properties=UIComponentProperties(
                label="HTTP Method",
                options=[
                    {"label": "GET", "value": "GET"},
                    {"label": "POST", "value": "POST"},
                    {"label": "PUT", "value": "PUT"},
                    {"label": "DELETE", "value": "DELETE"},
                    {"label": "PATCH", "value": "PATCH"},
                ],
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
        ComponentParameterDefinition(
            id=UUID("f6a7b8c9-d0e1-2345-f123-456789012345"),
            component_version_id=api_call_component_version.id,
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

    upsert_components_parameter_definitions(session, api_call_parameter_definitions)

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=api_call_component_version.component_id,
        release_stage=api_call_component_version.release_stage,
        component_version_id=api_call_component_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=api_call_component.id,
        category_ids=[CATEGORY_UUIDS["integrations"], CATEGORY_UUIDS["information_retrieval"]],
    )
