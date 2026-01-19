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
    Component,
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.seed.constants import (
    COMPLETION_MODEL_IN_DB,
    TEMPERATURE_IN_DB,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    ParameterLLMConfig,
    build_function_calling_service_config_definitions,
)


def seed_docx_template_components(session: Session):
    docx_template_component = Component(
        id=COMPONENT_UUIDS["docx_template"],
        name="DOCX Template Tool",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
    )
    upsert_components(session, [docx_template_component])

    docx_template_component_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["docx_template_agent"],
        component_id=COMPONENT_UUIDS["docx_template"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description=(
            "Analyze DOCX templates, generate content using AI based on business briefs, "
            "and fill templates with structured data."
        ),
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["docx_template_tool_description"],
    )
    upsert_component_versions(session, [docx_template_component_version])

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("12345678-90ab-cdef-1234-567890abcdef"),
                component_version_id=docx_template_component_version.id,
                name="additional_instructions",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Additional Instructions",
                    placeholder="Enter any additional instructions for the template filling process.",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("87654321-cdef-ab90-4321-987654321fed"),
                component_version_id=docx_template_component_version.id,
                name="template_base64",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.FILE_UPLOAD,
                ui_component_properties=UIComponentProperties(
                    label="Template (Docx)",
                    accept=".docx",
                    multiple=False,
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            *build_function_calling_service_config_definitions(
                component_version_id=docx_template_component_version.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("b2c3d4e5-f6a7-8901-bcde-f23456789012"),
                    ),
                    ParameterLLMConfig(
                        param_name=TEMPERATURE_IN_DB,
                        param_id=UUID("c3d4e5f6-a7b8-9012-cdef-345678901234"),
                    ),
                ],
            ),
        ],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=docx_template_component_version.component_id,
        release_stage=docx_template_component_version.release_stage,
        component_version_id=docx_template_component_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=docx_template_component.id,
        category_ids=[CATEGORY_UUIDS["file_generation"]],
    )
