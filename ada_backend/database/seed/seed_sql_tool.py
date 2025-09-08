from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ParameterType
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_child_relationships,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_completion_service_config_definitions,
)
from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB


def seed_sql_tool_components(session: Session):
    sql_tool = db.Component(
        id=COMPONENT_UUIDS["sql_tool"],
        name="SQLTool",
        description="SQL Tool for querying databases",
        is_agent=False,
        function_callable=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_tool_description"],
    )
    run_sql_query_tool = db.Component(
        id=COMPONENT_UUIDS["run_sql_query_tool"],
        name="RunSQLQueryTool",
        description="Run SQL Query Tool",
        is_agent=False,
        function_callable=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_run_sql_query_tool_description"],
    )
    upsert_components(
        session=session,
        components=[
            sql_tool,
            run_sql_query_tool,
        ],
    )
    # SQL Run Tool
    run_sql_tool_db_service_param = db.ComponentParameterDefinition(
        id=UUID("1160d57c-77cd-4a5c-a569-4c14fca875d6"),
        component_id=run_sql_query_tool.id,
        name="db_service",
        type=ParameterType.COMPONENT,
        nullable=False,
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[run_sql_tool_db_service_param],
    )
    upsert_components_parameter_child_relationships(
        session=session,
        component_parameter_child_relationships=[
            db.ComponentParameterChildRelationship(
                id=UUID("8440ddee-bc05-4274-bcec-877e9e978af1"),
                component_parameter_definition_id=run_sql_tool_db_service_param.id,
                child_component_id=COMPONENT_UUIDS["sql_db_service"],
            ),
        ],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # SQL Tool
            db.ComponentParameterDefinition(
                id=UUID("1e15c7d2-9f86-4428-8722-b39b8ddafac8"),
                component_id=sql_tool.id,
                name="db_service",
                type=ParameterType.COMPONENT,
                nullable=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("1299b4db-4cc9-4a02-b4a0-16c2802281ee"),
                component_id=sql_tool.id,
                name="include_tables",
                type=ParameterType.STRING,
                nullable=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("4f2e918f-842a-4f32-b378-8b08c9cb9da9"),
                component_id=sql_tool.id,
                name="additional_db_description",
                type=ParameterType.STRING,
                nullable=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("4ffb10e0-b5cb-487e-970e-ef8decbf77da"),
                component_id=sql_tool.id,
                name="synthesize",
                type=ParameterType.BOOLEAN,
                default="False",
            ),
            *build_completion_service_config_definitions(
                component_id=sql_tool.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("978afae2-4a79-4f26-a3a1-0a64cbd75b82"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("2d093471-cfcc-42ee-a520-5d1d8c9f3d01"),
                    ),
                ],
            ),
        ],
    )
