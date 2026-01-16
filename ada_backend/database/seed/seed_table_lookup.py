import json
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
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
)

DEFAULT_TABLE_MAPPING = {
    "hello": "world",
}


def seed_table_lookup_components(session: Session):
    table_lookup = db.Component(
        id=COMPONENT_UUIDS["table_lookup"],
        name="Table Lookup",
        is_agent=True,
        function_callable=False,
        icon="tabler-table",
    )
    upsert_components(
        session=session,
        components=[
            table_lookup,
        ],
    )
    table_lookup_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["table_lookup"],
        component_id=COMPONENT_UUIDS["table_lookup"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="A table lookup component that performs key-value lookup based on a mapping dictionary.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_table_lookup_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[table_lookup_version],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("6a7b8c9d-0e1f-2345-6789-0abcdef12345"),
                component_version_id=table_lookup_version.id,
                name="table_mapping",
                type=ParameterType.STRING,
                nullable=False,
                default=json.dumps(DEFAULT_TABLE_MAPPING, indent=2),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Table Mapping",
                    description="JSON dictionary mapping input keys to output values. "
                    "Example: {\"hello\": \"world\"}",
                    placeholder='{\n  "key1": "value1",\n  "key2": "value2"\n}',
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("8c9d0e1f-2345-6789-0abc-def123456789"),
                component_version_id=table_lookup_version.id,
                name="default_value",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Default Value",
                    description="The value to return when the input key is not found in the mapping",
                    placeholder="Enter default value",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )
    upsert_component_categories(
        session=session,
        component_id=table_lookup.id,
        category_ids=[CATEGORY_UUIDS["workflow_logic"]],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=table_lookup.id,
        release_stage=table_lookup_version.release_stage,
        component_version_id=table_lookup_version.id,
    )
