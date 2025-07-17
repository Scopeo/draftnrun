from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS


def seed_merger_components(session: Session):
    merger = db.Component(
        id=COMPONENT_UUIDS["merger"],
        name="Merger",
        description="Merger: merges multiple AgentPayload instances into a single one",
        is_agent=True,
        is_protected=True,
        function_callable=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_merger_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            merger,
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("c3d4e5f6-7a8b-9c0d-1e2f-3a4b5c6d7e8f"),
                component_id=merger.id,
                name="separator",
                type=ParameterType.STRING,
                nullable=False,
                default="\\n",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Separator",
                    placeholder="\\n",
                    description="The separator to use when merging content pieces (e.g., '\\n' for newline).",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )
