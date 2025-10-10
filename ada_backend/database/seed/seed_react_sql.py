from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_child_relationships,
    upsert_components_parameter_definitions,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_function_calling_service_config_definitions,
)
from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB
from engine.agent.sql.react_sql_tool import DEFAULT_REACT_SQL_TOOL_PROMPT


def seed_react_sql_components(session: Session):
    react_sql_agent = db.Component(
        id=COMPONENT_UUIDS["react_sql_agent"],
        name="Database Query Agent",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=True,
        icon="tabler-database-cog",
    )
    upsert_components(
        session=session,
        components=[
            react_sql_agent,
        ],
    )
    react_sql_agent_version = db.ComponentVersion(
        id=COMPONENT_UUIDS["react_sql_agent"],
        component_id=COMPONENT_UUIDS["react_sql_agent"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="ReAct Agent with SQL query tools",
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_react_sql_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[react_sql_agent_version],
    )
    # ReAct SQL Agent
    react_sql_agent_param = db.ComponentParameterDefinition(
        id=UUID("3f510f8c-79e9-4cf0-abe3-880e89c9372d"),
        component_version_id=react_sql_agent_version.id,
        name="db_service",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[react_sql_agent_param],
    )
    upsert_components_parameter_child_relationships(
        session=session,
        component_parameter_child_relationships=[
            db.ComponentParameterChildRelationship(
                id=UUID("f4749274-abc6-4de7-8ef2-2e7424895151"),
                component_parameter_definition_id=react_sql_agent_param.id,
                child_component_version_id=COMPONENT_UUIDS["snowflake_db_service"],
            ),
            db.ComponentParameterChildRelationship(
                id=UUID("12e869f3-0465-4e47-a810-d79a4f9a7bd0"),
                component_parameter_definition_id=react_sql_agent_param.id,
                child_component_version_id=COMPONENT_UUIDS["sql_db_service"],
            ),
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("3253a083-0a54-4d7b-b438-6a7c13d67dc8"),
                component_version_id=react_sql_agent_version.id,
                name="include_tables",
                type=ParameterType.JSON,
                nullable=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("18baf91c-bdc2-4a14-a9db-bf573e2153d0"),
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
                id=UUID("69728a7d-0dd2-412d-b3d4-9348de3b92cd"),
                component_version_id=react_sql_agent_version.id,
                name="prompt",
                type=ParameterType.STRING,
                nullable=False,
                default=DEFAULT_REACT_SQL_TOOL_PROMPT,
            ),
            db.ComponentParameterDefinition(
                id=UUID("81ad2034-3c5e-4f10-bc57-1fe5ea450d92"),
                component_version_id=react_sql_agent_version.id,
                name="db_schema_name",
                type=ParameterType.STRING,
                nullable=True,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Schema Name",
                    placeholder="Enter the snowflake schema name",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            *build_function_calling_service_config_definitions(
                component_version_id=react_sql_agent_version.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("3d858a3a-1730-414f-9a57-45f72cbd3cfd"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("260e7556-824b-4798-9bf1-436bb6eeb7ec"),
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
