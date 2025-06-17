from fastapi.testclient import TestClient
import uuid
from unittest.mock import patch

from ada_backend.main import app
from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings
from ada_backend.schemas.ingestion_task_schema import IngestionTaskQueue, IngestionTaskUpdate
from ada_backend.schemas.source_schema import DataSourceSchema, DataSourceUpdateSchema
from ada_backend.database import models as db

client = TestClient(app)
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"  # umbrella organization
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}

HEADERS_API_KEY = {
    "x-ingestion-api-key": settings.INGESTION_API_KEY,
    "Content-Type": "application/json",
}

TEST_SOURCE_NAME = "Test Source"
TEST_SOURCE_TYPE = "local"
TEST_SOURCE_ATTRIBUTES = {"path": "test_path", "access_token": None}
DATABASE_SCHEMA = "test_schema"
DATABASE_TABLE_NAME = "test_table"
QDRANT_COLLECTION_NAME = "customer_service"


@patch("ada_backend.services.source_service.QdrantService")
@patch("ada_backend.services.source_service.SQLLocalService")
def test_ingestion_endpoints(mock_sql_local_service, mock_qdrant_service):
    mock_qdrant_instance = mock_qdrant_service.return_value
    mock_qdrant_instance.delete_collection.return_value = None

    mock_db_service_instance = mock_sql_local_service.return_value
    mock_db_service_instance.drop_table.return_value = None

    endpoint = f"/ingestion_task/{ORGANIZATION_ID}"
    payload = IngestionTaskQueue(
        source_name=TEST_SOURCE_NAME,
        source_type=db.SourceType.LOCAL,
        status=db.TaskStatus.PENDING,
        source_attributes=TEST_SOURCE_ATTRIBUTES,
    )
    response = client.post(endpoint, headers=HEADERS_JWT, json=payload.model_dump())
    task_id = response.json()

    assert response.status_code == 201
    assert isinstance(task_id, str)
    assert len(task_id) > 0

    source_payload = DataSourceSchema(
        name=TEST_SOURCE_NAME,
        type=db.SourceType.LOCAL,
        database_schema=DATABASE_SCHEMA,
        database_table_name=DATABASE_TABLE_NAME,
        qdrant_collection_name=QDRANT_COLLECTION_NAME,
    )
    response = client.post(
        f"/sources/{ORGANIZATION_ID}",
        headers=HEADERS_API_KEY,
        json=source_payload.model_dump(mode="json"),
    )
    source_id = response.json()

    assert response.status_code == 201
    assert len(source_id) > 0
    assert isinstance(source_id, str)

    update_source_payload = DataSourceUpdateSchema(
        id=source_id,
        name="Updated Source",
        type=db.SourceType.LOCAL,
        database_schema=DATABASE_SCHEMA,
        database_table_name=DATABASE_TABLE_NAME,
        qdrant_collection_name=QDRANT_COLLECTION_NAME,
    )
    update_source = client.patch(
        f"/sources/{ORGANIZATION_ID}",
        headers=HEADERS_JWT,
        json=update_source_payload.model_dump(mode="json"),
    )
    assert update_source.status_code == 200
    assert update_source.json() is None

    get_source_response = client.get(
        f"/sources/{ORGANIZATION_ID}",
        headers=HEADERS_JWT,
    )
    assert get_source_response.status_code == 200
    assert isinstance(get_source_response.json(), list)
    for source in get_source_response.json():
        if source["id"] == str(uuid.UUID(source_id)):
            assert source["name"] == "Updated Source"
            assert source["type"] == TEST_SOURCE_TYPE
            assert source["database_schema"] == DATABASE_SCHEMA
            assert source["database_table_name"] == DATABASE_TABLE_NAME

    update_payload = IngestionTaskUpdate(
        id=task_id,
        source_id=source_id,
        source_name="Updated Source",
        source_type=db.SourceType.LOCAL,
        status=db.TaskStatus.COMPLETED,
    )
    update_endpoint = f"/ingestion_task/{ORGANIZATION_ID}"
    update_response = client.patch(
        update_endpoint, headers=HEADERS_API_KEY, json=update_payload.model_dump(mode="json")
    )

    assert update_response.status_code == 200
    assert update_response.json() is None

    get_response = client.get(endpoint, headers=HEADERS_JWT)
    assert get_response.status_code == 200
    assert isinstance(get_response.json(), list)

    updated_task = next((item for item in get_response.json() if item["id"] == task_id), None)
    assert updated_task is not None
    assert updated_task["source_name"] == "Updated Source"
    assert updated_task["source_type"] == db.SourceType.LOCAL.value
    assert updated_task["status"] == "completed"

    delete_endpoint = f"/ingestion_task/{ORGANIZATION_ID}/{task_id}"
    delete_response = client.delete(delete_endpoint, headers=HEADERS_JWT)
    assert delete_response.status_code == 204

    delete_source_endpoint = f"/sources/{ORGANIZATION_ID}/{source_id}"
    delete_source_response = client.delete(delete_source_endpoint, headers=HEADERS_JWT)
    assert delete_source_response.status_code == 204
