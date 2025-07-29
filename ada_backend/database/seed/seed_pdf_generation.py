from uuid import UUID
from sqlalchemy.orm import Session

from ada_backend.database.models import (
    Component,
    ComponentParameterDefinition,
    UIComponent,
    UIComponentProperties,
    ParameterType,
)

from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database import models as db


def seed_pdf_generation_components(session: Session):
    pdf_generation_component = Component(
        id=COMPONENT_UUIDS["pdf_generation"],
        name="PDF Generation Tool",
        description="Convert markdown text to PDF files.",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_pdf_generation_tool_description"],
    )
    upsert_components(session, [pdf_generation_component])

    pdf_generation_parameter_definitions = [
        ComponentParameterDefinition(
            id=UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
            component_id=pdf_generation_component.id,
            name="markdown_content",
            type=ParameterType.STRING,
            nullable=False,
            ui_component=UIComponent.TEXTAREA,
            ui_component_properties=UIComponentProperties(
                label="Markdown Content",
                placeholder="# Sample Markdown\n\nEnter your markdown content here...",
                description="The markdown text to convert to PDF format.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        ),
    ]

    upsert_components_parameter_definitions(session, pdf_generation_parameter_definitions)
