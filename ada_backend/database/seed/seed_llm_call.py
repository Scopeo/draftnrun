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
from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties
from ada_backend.database.seed.constants import (
    COMPLETION_MODEL_IN_DB,
    REASONING_IN_DB,
    TEMPERATURE_IN_DB,
    VERBOSITY_IN_DB,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
    build_components_parameters_assignments_to_parameter_groups,
    build_parameters_group,
    build_parameters_group_definitions,
)

# Parameter IDs for LLM Call
LLM_CALL_PARAMETER_IDS = {
    "prompt_template": UUID("e79b8f5f-d9cc-4a1f-a98a-4992f42a0196"),
    "file_content_key": UUID("a12eb38c-a10e-46f8-bc31-01d3551d954c"),
    "file_url_key": UUID("0dcee65b-d3b7-43e6-8cb4-2ec531c1875c"),
    "output_format": UUID("d7ee43ab-80f8-4ee5-ac38-938163933610"),
    COMPLETION_MODEL_IN_DB: UUID("1233f6b4-cfab-44f6-bf62-f6e0a1b95db1"),
    TEMPERATURE_IN_DB: UUID("7645d690-45c1-4b3e-bcdc-babf0808f97d"),
    VERBOSITY_IN_DB: UUID("76c4361d-06f4-41dd-9c6c-cf66292de155"),
    REASONING_IN_DB: UUID("9863153f-d43c-46e5-bec9-9bef1deff2b4"),
    "api_key": UUID("a9acc79a-bd8c-4406-89ef-9d3d88f50138"),
}

# Parameter Group UUIDs for LLM Call
LLM_CALL_PARAMETER_GROUP_UUIDS = {
    "advanced_llm_parameters": UUID("f6a7b8c9-d0e1-2345-f123-456789012345"),
}


def seed_llm_call_components(session: Session):
    llm_call = db.Component(
        id=COMPONENT_UUIDS["llm_call"],
        name="AI",
        is_agent=True,
        function_callable=True,
        icon="tabler-message-chatbot",
    )
    upsert_components(
        session=session,
        components=[
            llm_call,
        ],
    )
    llm_call_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["llm_call"],
        component_id=COMPONENT_UUIDS["llm_call"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="A component that makes calls to a Large Language Model (LLM) with a custom prompt.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_llm_call_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[llm_call_version],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("e79b8f5f-d9cc-4a1f-a98a-4992f42a0196"),
                component_version_id=llm_call_version.id,
                name="prompt_template",
                type=ParameterType.STRING,
                nullable=False,
                default="Answer this question: {{input}}",
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Prompt Template",
                    placeholder=(
                        "Enter the prompt here. Use {{input}} (or similar) to insert dynamic content "
                        "-  the {{}} braces with a keyword are mandatory."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("a12eb38c-a10e-46f8-bc31-01d3551d954c"),
                component_version_id=llm_call_version.id,
                name="file_content_key",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="File content key",
                    placeholder="file_content",
                    description=(
                        "Reference the output key from the previous component that contains the file content."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("0dcee65b-d3b7-43e6-8cb4-2ec531c1875c"),
                component_version_id=llm_call_version.id,
                name="file_url_key",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="File URL key",
                    placeholder="file_url",
                    description=("Reference the output key from the previous component that contains the file URL."),
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("d7ee43ab-80f8-4ee5-ac38-938163933610"),
                component_version_id=llm_call_version.id,
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
                component_version_id=llm_call_version.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("1233f6b4-cfab-44f6-bf62-f6e0a1b95db1"),
                    ),
                    ParameterLLMConfig(
                        param_name=TEMPERATURE_IN_DB,
                        param_id=UUID("7645d690-45c1-4b3e-bcdc-babf0808f97d"),
                    ),
                    ParameterLLMConfig(
                        param_name=VERBOSITY_IN_DB,
                        param_id=UUID("76c4361d-06f4-41dd-9c6c-cf66292de155"),
                    ),
                    ParameterLLMConfig(
                        param_name=REASONING_IN_DB,
                        param_id=UUID("9863153f-d43c-46e5-bec9-9bef1deff2b4"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("a9acc79a-bd8c-4406-89ef-9d3d88f50138"),
                    ),
                ],
            ),
        ],
    )

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=llm_call_version.component_id,
        release_stage=llm_call_version.release_stage,
        component_version_id=llm_call_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=llm_call.id,
        category_ids=[CATEGORY_UUIDS["ai"]],
    )


def seed_llm_call_parameter_groups(session: Session):
    """Seed parameter groups for LLM Call component."""

    parameter_groups = [
        db.ParameterGroup(
            id=LLM_CALL_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"], name="Advanced LLM Parameters"
        ),
    ]
    build_parameters_group(session, parameter_groups)

    component_parameter_groups = [
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_UUIDS["llm_call"],
            parameter_group_id=LLM_CALL_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            group_order_within_component=1,
        ),
    ]
    build_parameters_group_definitions(session, component_parameter_groups)

    parameter_group_assignments = {
        # Advanced LLM Parameters Group
        LLM_CALL_PARAMETER_IDS[TEMPERATURE_IN_DB]: {
            "parameter_group_id": LLM_CALL_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 1,
        },
        LLM_CALL_PARAMETER_IDS[VERBOSITY_IN_DB]: {
            "parameter_group_id": LLM_CALL_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 2,
        },
        LLM_CALL_PARAMETER_IDS[REASONING_IN_DB]: {
            "parameter_group_id": LLM_CALL_PARAMETER_GROUP_UUIDS["advanced_llm_parameters"],
            "parameter_order_within_group": 3,
        },
    }
    build_components_parameters_assignments_to_parameter_groups(session, parameter_group_assignments)

    session.commit()
