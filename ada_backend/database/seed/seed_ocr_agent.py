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
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_ocr_service_config_definitions,
)
from ada_backend.services.registry import COMPLETION_MODEL_IN_DB


def seed_ocr_agent_components(session: Session):
    ocr_agent = db.Component(
        id=COMPONENT_UUIDS["ocr_agent"],
        name="OCR Agent",
        description="Extract text from PDF files using OCR (Optical Character Recognition)",
        is_agent=True,
        function_callable=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            ocr_agent,
        ],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("b1c2d3e4-f5a6-7890-1234-56789abcdef0"),
                component_id=ocr_agent.id,
                name="file_content",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="File Content Reference",
                    placeholder="{file_content}",
                    description=(
                        "Reference the output key from the previous component that contains the file content. "
                        "Use the placeholder {file_content} to dynamically insert this content. "
                        "The curly braces {} with the keyword are required for proper substitution."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            *build_ocr_service_config_definitions(
                component_id=ocr_agent.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("329f22ec-0382-4fcf-963f-3281e68e6224"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("d3e4f5a6-b7c8-9012-3456-789abcdef012"),
                    ),
                ],
            ),
        ],
    )
