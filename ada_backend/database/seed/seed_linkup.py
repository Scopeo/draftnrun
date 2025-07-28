from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.integrations.seed_integration import INTEGRATION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_web_service_config_definitions,
)
from ada_backend.services.registry import COMPLETION_MODEL_IN_DB


def seed_linkup_components(session: Session):
    linkup_component = db.Component(
        id=COMPONENT_UUIDS["linkup_service"],
        name="Linkup Service",
        description="Linkup integration service for connecting and linking various platforms and data sources",
        is_agent=False,
        integration_id=INTEGRATION_UUIDS["linkup_service"],
        function_callable=True,
        can_use_function_calling=True,
        release_stage=db.ReleaseStage.BETA,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["linkup_tool_description"],
    )
    
    upsert_components(
        session=session,
        components=[
            linkup_component,
        ],
    )
    
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # Linkup Service Component parameters
            *build_web_service_config_definitions(
                component_id=linkup_component.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("a1b2c3d4-5e6f-7890-abcd-ef1234567890"),
                    ),
                    ParameterLLMConfig(
                        param_name="base_url",
                        param_id=UUID("b2c3d4e5-6f78-90ab-cdef-123456789012"),
                    ),
                    ParameterLLMConfig(
                        param_name="timeout",
                        param_id=UUID("c3d4e5f6-7890-abcd-ef12-3456789abcde"),
                    ),
                ],
            ),
        ],
    )