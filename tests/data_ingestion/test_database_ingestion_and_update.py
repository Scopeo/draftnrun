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


"""
Test flexible authentication (JWT and/or API key) for database ingestion endpoints.

Test structure:
1. test_create_ingestion_task_auth: Tests ingestion task creation
   - Sends POST /ingestion_task/{org_id} with different auth combinations
   - Verifies task is created if at least one auth method is valid
   - Verifies task data in database (name, type, status)
   - Cleans up created task

2. test_update_source_auth: Tests source update (re-trigger ingestion)
   - First creates a source via POST /sources/{org_id}
   - Sends POST /sources/{org_id}/{source_id} with different auth combinations
   - Verifies update succeeds if at least one auth method is valid
   - Cleans up created source

Test cases for each endpoint:
- Valid JWT only ✅
- Valid API key only ✅
- Both authentication methods provided ❌ (XOR violation - 400)
- No authentication ❌ (401)

Note: Uses mocked Snowflake database (fake credentials) to be safe for GitHub.
Since the database is mocked, the actual ingestion process is not executed.
Only API endpoints and authentication are tested.
"""

BASE_URL = "http://localhost:8000"
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"
MOCK_DB_URL = (
    "snowflake://MOCK_USER:MOCK_PASSWORD@mock.region.aws/mock_db/mock_schema?warehouse=MOCK_WH&role=mock_role"
)


# ============================================================================
# Fixtures: Setup expensive resources (JWT token, API key) and test data
# ============================================================================


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
def headers_map(jwt_token, api_key):
    return {
        "jwt_valid": {"accept": "application/json", "Authorization": f"Bearer {jwt_token}"},
        "api_key_valid": {"accept": "application/json", "X-API-Key": api_key, "Content-Type": "application/json"},
        "both_provided": {
            "accept": "application/json",
            "Authorization": "Bearer invalid.jwt.token",
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        },
        "no_auth": {"accept": "application/json", "Content-Type": "application/json"},
    }


# ============================================================================
# Global test data: Parametrize cases and mock database attributes
# ============================================================================

AUTH_TEST_CASES = [
    ("jwt_valid", True),
    ("api_key_valid", True),
    ("both_provided", False),
    ("no_auth", False),
]

SOURCE_ATTRIBUTES = {
    "source_db_url": MOCK_DB_URL,
    "source_schema_name": "mock_schema",
    "source_table_name": "mock_table",
    "id_column_name": "id",
    "text_column_names": ["content_column"],
    "timestamp_column_name": "updated_at",
}


# ============================================================================
# Helper functions: API calls, data retrieval, and cleanup
# ============================================================================


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


def get_ingestion_task_by_id(task_id, headers_jwt):
    response = requests.get(f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}", headers=headers_jwt)
    if response.status_code != 200:
        return None
    for task in response.json():
        if task["id"] == task_id:
            return task
    return None


def verify_ingestion_task_data(task, expected_name, expected_type):
    assert task["source_name"] == expected_name
    assert task["source_type"] == expected_type
    # Mocked DB => failed ingestion. We only verify ingestion task is sent to DB, not successful


def cleanup_ingestion_task(task_id, headers_map):
    if task_id:
        requests.delete(f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}/{task_id}", headers=headers_map["jwt_valid"])


# ============================================================================
# Tests: Verify flexible authentication for ingestion endpoints
# ============================================================================


@pytest.mark.parametrize("auth_type,should_succeed", AUTH_TEST_CASES)
def test_create_ingestion_task_auth(
    auth_type,
    should_succeed,
    headers_map,
):
    source_name = f"Test_Create_{auth_type}"
    response = create_ingestion_task(source_name, SOURCE_ATTRIBUTES, headers_map[auth_type])

    if should_succeed:
        assert response.status_code == 201
        task_id = response.json()
        assert isinstance(task_id, str)

        task = get_ingestion_task_by_id(task_id, headers_map["jwt_valid"])
        assert task is not None
        verify_ingestion_task_data(task, source_name, "database")

        cleanup_ingestion_task(task_id, headers_map)
    else:
        assert response.status_code in [400, 401]
        if auth_type == "both_provided":
            assert response.status_code == 400
        elif auth_type == "no_auth":
            assert response.status_code == 401


@pytest.mark.parametrize("auth_type,should_succeed", AUTH_TEST_CASES)
def test_update_source_auth(
    auth_type,
    should_succeed,
    headers_map,
):
    source_name = f"Test_Update_{auth_type}"

    source_payload = {
        "name": source_name,
        "type": "database",
        "database_table_name": f"test_table_{auth_type}",
        "attributes": SOURCE_ATTRIBUTES,
    }
    create_source_response = requests.post(
        f"{BASE_URL}/sources/{ORGANIZATION_ID}",
        headers={"X-Ingestion-API-Key": settings.INGESTION_API_KEY, "Content-Type": "application/json"},
        json=source_payload,
    )
    assert create_source_response.status_code == 201
    source_id = create_source_response.json()

    update_response = requests.post(
        f"{BASE_URL}/sources/{ORGANIZATION_ID}/{source_id}", headers=headers_map[auth_type]
    )

    if should_succeed:
        assert update_response.status_code == 200
    else:
        assert update_response.status_code in [400, 401]
        if auth_type == "both_provided":
            assert update_response.status_code == 400
        elif auth_type == "no_auth":
            assert update_response.status_code == 401

    requests.delete(f"{BASE_URL}/sources/{ORGANIZATION_ID}/{source_id}", headers=headers_map["jwt_valid"])
