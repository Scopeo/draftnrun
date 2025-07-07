from uuid import UUID
import json

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

OUTPUT_SCHEMA_PARAMETER_NAME = "output_schema"


def seed_output_components(session: Session):
    output = db.Component(
        id=COMPONENT_UUIDS["output"],
        name="Output",
        description="Output: takes a json and filters it according to an output schema",
        is_agent=True,
        is_protected=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_output_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            output,
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("59443366-5b1f-5543-9fc5-57378f9aaf6e"),
                component_id=output.id,
                name=OUTPUT_SCHEMA_PARAMETER_NAME,
                type=ParameterType.STRING,
                nullable=False,
                default=json.dumps(
                    {"response": "The final response", "confidence": 0.9}, indent=4
                ),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="""An example of your output schema""",
                    placeholder="An output schema for filtering the final response. Must be a correct "
                    "json schema that defines the structure of the expected output.",
                    description="Describe here the output schema for filtering the final workflow response."
                    " Must be a correct json schema. The output will be validated against this schema"
                    " and filtered to only include the specified fields.",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    ) 