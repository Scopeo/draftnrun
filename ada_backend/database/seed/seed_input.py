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

INPUT_PAYLOAD_PARAMETER_NAME = "payload_schema"


def seed_input_components(session: Session):
    input = db.Component(
        id=COMPONENT_UUIDS["input"],
        name="Input",
        description="Input: takes a json and output an AgentPayload",
        is_agent=True,
        is_protected=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            input,
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("48332255-4a0e-4432-8fb4-46267e8ffd4d"),
                component_id=input.id,
                name=INPUT_PAYLOAD_PARAMETER_NAME,
                type=ParameterType.STRING,
                nullable=False,
                default=json.dumps(
                    {"messages": [{"role": "user", "content": "Hello"}], "additional_info": "info"}, indent=4
                ),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="""An exemple of your payload schema""",
                    placeholder="A payload schema of your input for the pipeline. Must be a correct "
                    "api-formatted json. To connect to agents, the messages key with openai message format"
                    " is mandatory",
                    description="Describe here the payload schema of your input for the workflow."
                    " Must be a correct json. The keys of this dictonary can be used in next components"
                    " as variables, for example: {{additional_info}}",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )
