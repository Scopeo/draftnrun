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
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
)
from ada_backend.services.registry import COMPLETION_MODEL_IN_DB


def seed_llm_call_components(session: Session):
    llm_call = db.Component(
        id=COMPONENT_UUIDS["llm_call"],
        name="LLM Call",
        description="Templated LLM Call",
        is_agent=True,
        function_callable=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            llm_call,
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("e79b8f5f-d9cc-4a1f-a98a-4992f42a0196"),
                component_id=llm_call.id,
                name="prompt_template",
                type=ParameterType.STRING,
                nullable=False,
                default="Answer this question: {input}",
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Prompt Template",
                    placeholder=(
                        "Enter the prompt here. Use {input} (or similar) to insert dynamic content "
                        "-  the {} braces with a keyword are mandatory."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("a12eb38c-a10e-46f8-bc31-01d3551d954c"),
                component_id=llm_call.id,
                name="file_content",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="File content",
                    placeholder="{file_content}",
                    description=(
                        "Reference the output key from the previous component that contains the file content. "
                        "Use the placeholder {file_content} to dynamically insert this content. "
                        "The curly braces {} with the keyword are required for proper substitution."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("d7ee43ab-80f8-4ee5-ac38-938163933610"),
                component_id=llm_call.id,
                name="output_format",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Output Format",
                    placeholder=(
                        json.dumps(
                            {
                                "name": "weather_data",
                                "strict": True,
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "location": {
                                            "type": "string",
                                            "description": "The location to get the weather for",
                                        },
                                        "unit": {
                                            "type": ["string", "null"],
                                            "description": "The unit to return the temperature in",
                                            "enum": ["F", "C"],
                                        },
                                        "value": {
                                            "type": "number",
                                            "description": "The actual temperature value in the location",
                                            "minimum": -130,
                                            "maximum": 130,
                                        },
                                    },
                                    "additionalProperties": False,
                                    "required": ["location", "unit", "value"],
                                },
                            },
                            indent=4,
                        )
                    ),
                    description=(
                        "Enter the output format here using this documentation from OpenAI: "
                        "https://platform.openai.com/docs/guides/structured-outputs#supported-schemas"
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            *build_completion_service_config_definitions(
                component_id=llm_call.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("1233f6b4-cfab-44f6-bf62-f6e0a1b95db1"),
                    ),
                    ParameterLLMConfig(
                        param_name="default_temperature",
                        param_id=UUID("7645d690-45c1-4b3e-bcdc-babf0808f97d"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("a9acc79a-bd8c-4406-89ef-9d3d88f50138"),
                    ),
                ],
            ),
        ],
    )
