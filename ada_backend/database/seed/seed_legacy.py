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


def seed_legacy_components(session: Session):
    # --- Define Agents ---
    switch_categorical_pipeline = db.Component(
        id=COMPONENT_UUIDS["switch_categorical_pipeline"],
        name="SwitchCategoricalPipeline",
        description="Switch pipeline for categorical agents",
        is_agent=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    static_responder = db.Component(
        id=COMPONENT_UUIDS["static_responder"],
        name="StaticResponder",
        description="Static responder for a predefined response",
        is_agent=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    sequential_pipeline = db.Component(
        id=COMPONENT_UUIDS["sequential_pipeline"],
        name="SequentialPipeline",
        description="Sequential pipeline for sequential agents",
        is_agent=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            switch_categorical_pipeline,
            static_responder,
            sequential_pipeline,
        ],
    )

    # Parameter Definitions
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # Switch Categorical Pipeline
            db.ComponentParameterDefinition(
                id=UUID("6b5114cf-726b-4f94-b68f-0e6e0d1fc189"),
                component_id=switch_categorical_pipeline.id,
                name="agents",
                type=ParameterType.COMPONENT,
                nullable=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("5b334eb6-9a41-44de-b4b1-49beabdc65e0"),
                component_id=switch_categorical_pipeline.id,
                name="categories",
                type=ParameterType.STRING,
                nullable=False,
            ),
            # Sequential Pipeline
            db.ComponentParameterDefinition(
                id=UUID("74048f04-0b2e-4c29-9910-b7fe1fd7bc5c"),
                component_id=sequential_pipeline.id,
                name="agents",
                type=ParameterType.COMPONENT,
                nullable=False,
            ),
            # Static Responder
            db.ComponentParameterDefinition(
                id=UUID("b72a23cf-bf49-49ed-84b2-79d79b24f017"),
                component_id=static_responder.id,
                name="response",
                type=ParameterType.STRING,
                nullable=False,
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Response", placeholder="Enter the static response here"
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )
