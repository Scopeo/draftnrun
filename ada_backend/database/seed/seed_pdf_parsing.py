from uuid import UUID
from sqlalchemy.orm import Session

from ada_backend.database.models import Component, ParameterType, UIComponent, UIComponentProperties

from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_component_categories,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database import models as db


def seed_pdf_parsing_components(session: Session):
    pdf_parsing_component = Component(
        id=COMPONENT_UUIDS["pdf_parsing_tool"],
        name="PDF Parsing Tool",
        description="Parse PDF files and convert them to markdown text for further processing in workflows.",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["pdf_parsing_tool_description"],
        icon="tabler-file-type-pdf",
    )
    upsert_components(session, [pdf_parsing_component])

    upsert_component_categories(
        session=session,
        component_id=pdf_parsing_component.id,
        category_ids=[CATEGORY_UUIDS["processing"]],
    )
