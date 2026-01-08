from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
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
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS


def seed_db_service_components(session: Session):
    sql_db_service = db.Component(
        id=COMPONENT_UUIDS["sql_db_service"],
        name="SQLDBService",
    )
    snowflake_db_service = db.Component(
        id=COMPONENT_UUIDS["snowflake_db_service"],
        name="SnowflakeDBService",
    )
    upsert_components(
        session=session,
        components=[
            sql_db_service,
            snowflake_db_service,
        ],
    )

    sql_db_service_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["sql_db_service"],
        component_id=COMPONENT_UUIDS["sql_db_service"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="SQL Database service for querying databases",
    )
    snowflake_db_service_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["snowflake_db_service"],
        component_id=COMPONENT_UUIDS["snowflake_db_service"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        description="SQL Database service for querying databases with snowflake",
    )
    upsert_component_versions(
        session=session,
        component_versions=[
            sql_db_service_version,
            snowflake_db_service_version,
        ],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # SQL DB Service
            db.ComponentParameterDefinition(
                id=UUID("86a74912-4d9c-4f0a-a504-3778d9f4b99c"),
                component_version_id=sql_db_service_version.id,
                name="engine_url",
                type=ParameterType.STRING,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Engine URL",
                    placeholder="e.g., postgresql://user:password@localhost:5432/database",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            # Snowflake DB Service
            db.ComponentParameterDefinition(
                id=UUID("4012ef7a-ff8b-4e00-a4e4-d01f197b800f"),
                component_version_id=snowflake_db_service_version.id,
                name="database_name",
                type=ParameterType.STRING,
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Database Name",
                    placeholder="Enter the database name here",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("9f61fbe0-3e0e-4407-87f5-301e3ac14b06"),
                component_version_id=snowflake_db_service_version.id,
                name="role_to_use",
                type=ParameterType.STRING,
                default="SCOPEO_READ_ROLE",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Role",
                    placeholder="Enter the role to use here",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("23a5dbac-7978-4865-958c-badfe1826d84"),
                component_version_id=snowflake_db_service_version.id,
                name="warehouse",
                type=ParameterType.STRING,
                default="AIRBYTE_WAREHOUSE",
                ui_component=UIComponent.TEXTFIELD,
                ui_component_properties=UIComponentProperties(
                    label="Warehouse",
                    placeholder="Enter the warehouse here",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
        ],
    )

    # Create release stage mappings
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=sql_db_service_version.component_id,
        release_stage=sql_db_service_version.release_stage,
        component_version_id=sql_db_service_version.id,
    )
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=snowflake_db_service_version.component_id,
        release_stage=snowflake_db_service_version.release_stage,
        component_version_id=snowflake_db_service_version.id,
    )
