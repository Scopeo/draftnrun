from sqlalchemy.orm import Session

from ada_backend.database.models import Component

from ada_backend.database.component_definition_seeding import upsert_components, upsert_component_categories
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database import models as db


def seed_docx_generation_components(session: Session):
    docx_generation_component = Component(
        id=COMPONENT_UUIDS["docx_generation"],
        name="DOCX Generation Tool",
        description="Convert markdown text to DOCX files.",
        is_agent=False,
        function_callable=True,
        can_use_function_calling=False,
        release_stage=db.ReleaseStage.INTERNAL,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_docx_generation_tool_description"],
        icon="tabler-file-type-docx",
    )
    upsert_components(session, [docx_generation_component])
    upsert_component_categories(
        session=session,
        component_id=docx_generation_component.id,
        category_ids=[CATEGORY_UUIDS["action"]],
    )
