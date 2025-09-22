from uuid import UUID
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_ocr_service_config_definitions,
)
from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB


def seed_ocr_call_components(session: Session):
    ocr_call = db.Component(
        id=COMPONENT_UUIDS["ocr_call"],
        name="OCR Call",
        is_agent=True,
        function_callable=True,
        icon="tabler-text-scan-2",
    )
    upsert_components(
        session=session,
        components=[
            ocr_call,
        ],
    )

    ocr_call_version = db.ComponentVersion(
        id=COMPONENT_UUIDS["ocr_call"],
        component_id=COMPONENT_UUIDS["ocr_call"],
        version_tag="1.0.0",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Extract text from PDF files using OCR (Optical Character Recognition)",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[ocr_call_version],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            *build_ocr_service_config_definitions(
                component_version_id=ocr_call_version.id,
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
    upsert_component_categories(
        session=session,
        component_id=ocr_call.id,
        category_ids=[CATEGORY_UUIDS["processing"]],
    )
