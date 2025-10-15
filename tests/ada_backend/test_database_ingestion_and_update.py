import pytest
import requests
import jwt
from uuid import UUID

from ada_backend.database.setup_db import SessionLocal
from ada_backend.scripts.get_supabase_token import get_user_jwt
from ada_backend.schemas.ingestion_task_schema import IngestionTaskQueue
from ada_backend.database import models as db
from ada_backend.services.api_key_service import generate_scoped_api_key
from settings import settings

BASE_URL = "http://localhost:8000"
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"
MOCK_DB_URL = (
    "snowflake://MOCK_USER:MOCK_PASSWORD@mock.region.aws/mock_db/mock_schema?warehouse=MOCK_WH&role=mock_role"
)


@pytest.fixture(scope="module")
def jwt_token():
    return get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)


@pytest.fixture(scope="module")
def api_key(jwt_token):
    decoded_token = jwt.decode(jwt_token, options={"verify_signature": False})
    user_id = UUID(decoded_token["sub"])

    session = SessionLocal()
    try:
        api_key_response = generate_scoped_api_key(
            session=session,
            scope_type=db.ApiKeyType.ORGANIZATION,
            scope_id=UUID(ORGANIZATION_ID),
            key_name="test_db_ingestion_key",
            creator_user_id=user_id,
        )
        session.commit()
        return api_key_response.private_key
    finally:
        session.close()


@pytest.fixture
def headers_jwt(jwt_token):
    return {"accept": "application/json", "Authorization": f"Bearer {jwt_token}"}


@pytest.fixture
def headers_api_key(api_key):
    return {"accept": "application/json", "X-API-Key": api_key, "Content-Type": "application/json"}


@pytest.fixture
def headers_invalid_jwt():
    return {"accept": "application/json", "Authorization": "Bearer invalid.jwt.token"}


@pytest.fixture
def headers_invalid_api_key():
    return {"accept": "application/json", "X-API-Key": "invalid_key_123", "Content-Type": "application/json"}


@pytest.fixture
def source_attributes():
    return {
        "source_db_url": MOCK_DB_URL,
        "source_schema_name": "mock_schema",
        "source_table_name": "mock_table",
        "id_column_name": "id",
        "text_column_names": ["content_column"],
        "timestamp_column_name": "updated_at",
    }


def create_ingestion_task(source_name, source_attributes, headers):
    payload = IngestionTaskQueue(
        source_name=source_name,
        source_type=db.SourceType.DATABASE,
        status=db.TaskStatus.PENDING,
        source_attributes=source_attributes,
    )
    response = requests.post(
        f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}", headers=headers, json=payload.model_dump()
    )
    return response


def get_source_by_name(source_name, headers_jwt):
    response = requests.get(f"{BASE_URL}/sources/{ORGANIZATION_ID}", headers=headers_jwt)
    if response.status_code != 200:
        return None
    for source in response.json():
        if source["name"] == source_name:
            return source
    return None


def verify_source_data(source, expected_name, expected_attributes):
    assert source["name"] == expected_name
    assert source["type"] == "database"
    assert source["attributes"]["source_db_url"] == expected_attributes["source_db_url"]
    assert source["attributes"]["source_schema_name"] == expected_attributes["source_schema_name"]
    assert source["attributes"]["source_table_name"] == expected_attributes["source_table_name"]
    assert source["attributes"]["id_column_name"] == expected_attributes["id_column_name"]
    assert source["attributes"]["text_column_names"] == expected_attributes["text_column_names"]


def cleanup_source(task_id, source_id, headers_jwt):
    if task_id:
        requests.delete(f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}/{task_id}", headers=headers_jwt)
    if source_id:
        requests.delete(f"{BASE_URL}/sources/{ORGANIZATION_ID}/{source_id}", headers=headers_jwt)


@pytest.mark.parametrize(
    "auth_type,should_succeed",
    [
        ("jwt_valid", True),
        ("api_key_valid", True),
        ("jwt_invalid_api_valid", True),
        ("jwt_valid_api_invalid", True),
        ("both_invalid", False),
        ("no_auth", False),
    ],
)
def test_create_ingestion_task_auth(
    auth_type,
    should_succeed,
    source_attributes,
    headers_jwt,
    headers_api_key,
    headers_invalid_jwt,
    headers_invalid_api_key,
    api_key,
):
    headers_map = {
        "jwt_valid": headers_jwt,
        "api_key_valid": headers_api_key,
        "jwt_invalid_api_valid": {**headers_invalid_jwt, "X-API-Key": api_key, "Content-Type": "application/json"},
        "jwt_valid_api_invalid": {**headers_jwt, "X-API-Key": "invalid_key"},
        "both_invalid": {**headers_invalid_jwt, "X-API-Key": "invalid_key"},
        "no_auth": {"accept": "application/json", "Content-Type": "application/json"},
    }

    source_name = f"Test_Create_{auth_type}"
    response = create_ingestion_task(source_name, source_attributes, headers_map[auth_type])

    if should_succeed:
        assert response.status_code == 201
        task_id = response.json()
        assert isinstance(task_id, str)

        source = get_source_by_name(source_name, headers_jwt)
        assert source is not None
        verify_source_data(source, source_name, source_attributes)

        cleanup_source(task_id, source["id"], headers_jwt)
    else:
        assert response.status_code in [401, 403]


@pytest.mark.parametrize(
    "auth_type,should_succeed",
    [
        ("jwt_valid", True),
        ("api_key_valid", True),
        ("jwt_invalid_api_valid", True),
        ("jwt_valid_api_invalid", True),
        ("both_invalid", False),
        ("no_auth", False),
    ],
)
def test_update_source_auth(
    auth_type,
    should_succeed,
    source_attributes,
    headers_jwt,
    headers_api_key,
    headers_invalid_jwt,
    api_key,
):
    headers_map = {
        "jwt_valid": headers_jwt,
        "api_key_valid": headers_api_key,
        "jwt_invalid_api_valid": {**headers_invalid_jwt, "X-API-Key": api_key, "Content-Type": "application/json"},
        "jwt_valid_api_invalid": {**headers_jwt, "X-API-Key": "invalid_key"},
        "both_invalid": {**headers_invalid_jwt, "X-API-Key": "invalid_key"},
        "no_auth": {"accept": "application/json", "Content-Type": "application/json"},
    }

    source_name = f"Test_Update_{auth_type}"
    create_response = create_ingestion_task(source_name, source_attributes, headers_jwt)
    assert create_response.status_code == 201
    task_id = create_response.json()

    source = get_source_by_name(source_name, headers_jwt)
    assert source is not None
    verify_source_data(source, source_name, source_attributes)

    update_response = requests.post(
        f"{BASE_URL}/sources/{ORGANIZATION_ID}/{source['id']}", headers=headers_map[auth_type]
    )

    if should_succeed:
        assert update_response.status_code == 200
    else:
        assert update_response.status_code in [401, 403]

    cleanup_source(task_id, source["id"], headers_jwt)
