from uuid import UUID
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
)
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
)


def seed_static_responder_components(session: Session):
    static_responder = db.Component(
        id=COMPONENT_UUIDS["static_responder"],
        name="Static Responder",
        description="A static responder tool that responds with a static message.",
        is_agent=True,
        function_callable=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            static_responder,
        ],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("c8a0b5a8-3b1a-4b0e-9c6a-7b3b7e0b5c1a"),
                component_id=static_responder.id,
                name="static_message",
                type=ParameterType.STRING,
                nullable=False,
                default="",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Static Message",
                    placeholder="Enter the static message to be returned.",
                ).model_dump(exclude_unset=True, exclude_none=True),
            )
        ],
    )
    upsert_component_categories(
        session=session,
        component_id=static_responder.id,
        category_ids=[CATEGORY_UUIDS["processing"]],
    )
