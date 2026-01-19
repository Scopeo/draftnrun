from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.models import Component
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


def seed_docx_generation_components(session: Session):
    docx_generation_component = Component(
        id=COMPONENT_UUIDS["docx_generation"],
        name="DOCX Generation Tool",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="tabler-file-type-docx",
    )
    upsert_components(session, [docx_generation_component])
    docx_generation_component_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["docx_generation"],
        component_id=COMPONENT_UUIDS["docx_generation"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.INTERNAL,
        description="Convert markdown text to DOCX files.",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_docx_generation_tool_description"],
    )
    upsert_component_versions(session, [docx_generation_component_version])

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=docx_generation_component_version.component_id,
        release_stage=docx_generation_component_version.release_stage,
        component_version_id=docx_generation_component_version.id,
    )

    upsert_component_categories(
        session=session,
        component_id=docx_generation_component.id,
        category_ids=[CATEGORY_UUIDS["file_generation"]],
    )
