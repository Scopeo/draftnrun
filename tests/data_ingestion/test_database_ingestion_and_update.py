from uuid import UUID

import jwt
import pytest

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.schemas.ingestion_task_schema import IngestionTaskQueue
from ada_backend.schemas.source_schema import DataSourceSchema
from ada_backend.scripts.get_supabase_token import get_user_jwt
from ada_backend.services.api_key_service import generate_scoped_api_key, verify_api_key
from ada_backend.services.ingestion_task_service import (
    create_ingestion_task_by_organization,
    delete_ingestion_task_by_id,
    get_ingestion_task_by_organization_id,
)
from ada_backend.repositories.source_repository import delete_source
from ada_backend.services.source_service import (
    create_source_by_organization,
    update_source_by_source_id,
)
from settings import settings

ORGANIZATION_ID = UUID("37b7d67f-8f29-4fce-8085-19dea582f605")
MOCK_DB_URL = (
    "snowflake://MOCK_USER:MOCK_PASSWORD@mock.region.aws/mock_db/mock_schema?warehouse=MOCK_WH&role=mock_role"
)


# Fixtures: Setup expensive resources (JWT token, API key) and test data
@pytest.fixture(scope="module")
def jwt_token():
    return get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)


@pytest.fixture(scope="module")
def api_key(jwt_token):
    decoded_token = jwt.decode(jwt_token, options={"verify_signature": False})
    user_id = UUID(decoded_token["sub"])

    with get_db_session() as session:
        api_key_response = generate_scoped_api_key(
            session=session,
            scope_type=db.ApiKeyType.ORGANIZATION,
            scope_id=ORGANIZATION_ID,
            key_name="test_db_ingestion_key",
            creator_user_id=user_id,
        )
        session.commit()
        return api_key_response.private_key


@pytest.fixture(scope="module")
def user_id(jwt_token):
    decoded_token = jwt.decode(jwt_token, options={"verify_signature": False})
    return UUID(decoded_token["sub"])


@pytest.fixture(scope="module")
def api_key_id(api_key):
    with get_db_session() as session:
        verified_key = verify_api_key(session, api_key)
        return verified_key.api_key_id


# Global test data: Parametrize authentication cases and mock database attributes
AUTH_TEST_CASES = [
    "user_id",
    "api_key_id",
]

SOURCE_ATTRIBUTES = {
    "source_db_url": MOCK_DB_URL,
    "source_schema_name": "mock_schema",
    "source_table_name": "mock_table",
    "id_column_name": "id",
    "text_column_names": ["content_column"],
    "timestamp_column_name": "updated_at",
}


# Helper functions: API calls, data retrieval, and cleanup
def create_ingestion_task(source_name, source_attributes, user_id=None, api_key_id=None):
    payload = IngestionTaskQueue(
        source_name=source_name,
        source_type=db.SourceType.DATABASE,
        status=db.TaskStatus.PENDING,
        source_attributes=source_attributes,
    )
    with get_db_session() as session:
        return create_ingestion_task_by_organization(
            session=session,
            organization_id=ORGANIZATION_ID,
            ingestion_task_data=payload,
            user_id=user_id,
            api_key_id=api_key_id,
        )


def get_ingestion_task_by_id(task_id):
    with get_db_session() as session:
        tasks = get_ingestion_task_by_organization_id(session, ORGANIZATION_ID)
        task = next((t for t in tasks if t.id == task_id), None)
        return task


def verify_ingestion_task_data(task, expected_name, expected_type):
    assert task.source_name == expected_name
    assert task.source_type == expected_type
    # Mocked DB => failed ingestion. We only verify ingestion task is sent to DB, not successful


def cleanup_ingestion_task(task_id):
    if task_id:
        with get_db_session() as session:
            delete_ingestion_task_by_id(session, ORGANIZATION_ID, task_id)


# Test flexible authentication (JWT and/or API key) for database ingestion endpoints.
@pytest.mark.parametrize("auth_type", AUTH_TEST_CASES)
def test_create_ingestion_task_auth(
    auth_type,
    user_id,
    api_key_id,
):
    source_name = f"Test_Create_{auth_type}"
    
    if auth_type == "user_id":
        task_id = create_ingestion_task(source_name, SOURCE_ATTRIBUTES, user_id=user_id)
    else:
        task_id = create_ingestion_task(source_name, SOURCE_ATTRIBUTES, api_key_id=api_key_id)

    assert isinstance(task_id, UUID)

    task = get_ingestion_task_by_id(task_id)
    assert task is not None
    verify_ingestion_task_data(task, source_name, "database")

    cleanup_ingestion_task(task_id)


@pytest.mark.parametrize("auth_type", AUTH_TEST_CASES)
def test_update_source_auth(
    auth_type,
    user_id,
    api_key_id,
):
    source_name = f"Test_Update_{auth_type}"

    source_payload = DataSourceSchema(
        name=source_name,
        type=db.SourceType.DATABASE,
        database_table_name=f"test_table_{auth_type}",
        attributes=SOURCE_ATTRIBUTES,
    )
    
    with get_db_session() as session:
        source_id = create_source_by_organization(
            session=session,
            organization_id=ORGANIZATION_ID,
            source_data=source_payload,
        )

        if auth_type == "user_id":
            update_source_by_source_id(
                session=session,
                organization_id=ORGANIZATION_ID,
                source_id=source_id,
                user_id=user_id,
            )
        else:
            update_source_by_source_id(
                session=session,
                organization_id=ORGANIZATION_ID,
                source_id=source_id,
                api_key_id=api_key_id,
            )

        tasks = get_ingestion_task_by_organization_id(session, ORGANIZATION_ID)
        source_task = next((t for t in tasks if t.source_id == source_id), None)
        assert source_task is not None, "Ingestion task should be created when updating source"

        delete_source(session, ORGANIZATION_ID, source_id)
        if source_task:
            delete_ingestion_task_by_id(session, ORGANIZATION_ID, source_task.id)
