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


def seed_splitter_components(session: Session):
    splitter = db.Component(
        id=COMPONENT_UUIDS["splitter"],
        name="Splitter",
        description="Splitter: splits an AgentPayload into multiple chunks based on delimiter or chunk size",
        is_agent=True,
        is_protected=True,
        function_callable=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_splitter_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            splitter,
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("a1b2c3d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d"),
                component_id=splitter.id,
                name="delimiter",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Delimiter",
                    placeholder="\\n\\n",
                    description="The delimiter to split the content by (e.g., '\\n\\n' for paragraphs). "
                    "Either delimiter or chunk_size must be provided, but not both.",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("b2c3d4e5-6f7a-8b9c-0d1e-2f3a4b5c6d7e"),
                component_id=splitter.id,
                name="chunk_size",
                type=ParameterType.INTEGER,
                nullable=True,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Chunk Size",
                    placeholder="1000",
                    description="The maximum size of each chunk in characters. "
                    "Either delimiter or chunk_size must be provided, but not both.",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )
