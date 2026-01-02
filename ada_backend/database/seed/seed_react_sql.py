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
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB, TEMPERATURE_IN_DB
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    ParameterLLMConfig,
    build_function_calling_service_config_definitions,
)
from engine.components.sql.react_sql_tool import DEFAULT_REACT_SQL_TOOL_PROMPT


def seed_react_sql_components(session: Session):
    react_sql_agent = db.Component(
        id=COMPONENT_UUIDS["react_sql_agent"],
        name="Database Query Agent",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=False,
        icon="tabler-database-cog",
    )
    upsert_components(
        session=session,
        components=[
            react_sql_agent,
        ],
    )
    react_sql_agent_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["react_sql_agent_v2"],
        component_id=COMPONENT_UUIDS["react_sql_agent"],
        version_tag="0.1.0",
        release_stage=db.ReleaseStage.PUBLIC,
        description="Agent that can query databases",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_react_sql_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[react_sql_agent_version],
    )
    # ReAct SQL Agent - db_service handled by processor (like LLM service)
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("a3e69895-d0b2-4d99-8fc8-c5daddc05663"),
                component_version_id=react_sql_agent_version.id,
                name="engine_url",
                type=ParameterType.STRING,
                nullable=False,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Database Engine URL",
                    placeholder="e.g., postgresql://user:password@localhost:5432/database",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("06d6132e-4d2e-4540-97a3-70345120816d"),
                component_version_id=react_sql_agent_version.id,
                name="include_tables",
                type=ParameterType.JSON,
                nullable=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("35678901-2345-6789-0123-456789012345"),
                component_version_id=react_sql_agent_version.id,
                name="additional_db_description",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Additional DB Description",
                    placeholder="Enter additional database description here",
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("76543210-9876-5432-1098-765432109876"),
                component_version_id=react_sql_agent_version.id,
                name="prompt",
                type=ParameterType.STRING,
                nullable=False,
                default=DEFAULT_REACT_SQL_TOOL_PROMPT,
            ),
            *build_function_calling_service_config_definitions(
                component_version_id=react_sql_agent_version.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("12345678-9012-3456-7890-123456789012"),
                    ),
                    ParameterLLMConfig(
                        param_name=TEMPERATURE_IN_DB,
                        param_id=UUID("45678901-2345-6789-0123-456789012345"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("78901234-5678-9012-3456-789012345678"),
                    ),
                ],
            ),
        ],
    )
    upsert_component_categories(
        session=session,
        component_id=react_sql_agent.id,
        category_ids=[CATEGORY_UUIDS["query"]],
    )

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=react_sql_agent_version.component_id,
        release_stage=react_sql_agent_version.release_stage,
        component_version_id=react_sql_agent_version.id,
    )
