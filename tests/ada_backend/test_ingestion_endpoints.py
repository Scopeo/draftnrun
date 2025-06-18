import requests

from ada_backend.scripts.get_supabase_token import get_user_jwt
from ada_backend.schemas.ingestion_task_schema import IngestionTaskQueue
from ada_backend.database import models as db
from ingestion_script.ingest_folder_source import ingest_local_folder_source
from ingestion_script.utils import get_sanitize_names
from engine.qdrant_service import QdrantService
from engine.storage_service.local_service import SQLLocalService
from settings import settings

BASE_URL = "http://localhost:8000"
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

TEST_SOURCE_NAME = "Test_Ingestion_Local_Folder"
TEST_SOURCE_TYPE = "local"
TEST_SOURCE_ATTRIBUTES = {"path": "tests/resources/documents/sample.pdf", "access_token": None}
DATABASE_SCHEMA, DATABASE_TABLE_NAME, QDRANT_COLLECTION_NAME = get_sanitize_names(
    source_name=TEST_SOURCE_NAME,
    organization_id=ORGANIZATION_ID,
)


def test_ingest_local_folder_source():

    endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}"
    payload = IngestionTaskQueue(
        source_name=TEST_SOURCE_NAME,
        source_type=db.SourceType.LOCAL,
        status=db.TaskStatus.PENDING,
        source_attributes=TEST_SOURCE_ATTRIBUTES,
    )
    response = requests.post(endpoint, headers=HEADERS_JWT, json=payload.model_dump())
    task_id = response.json()

    assert response.status_code == 201
    assert isinstance(task_id, str)
    assert len(task_id) > 0

    ingest_local_folder_source(
        path=TEST_SOURCE_ATTRIBUTES["path"],
        organization_id=ORGANIZATION_ID,
        source_name=TEST_SOURCE_NAME,
        task_id=task_id,
        save_supabase=False,
        add_doc_description_to_chunks=False,
    )
    get_source_response = requests.get(
        f"{BASE_URL}/sources/{ORGANIZATION_ID}",
        headers=HEADERS_JWT,
    )
    assert get_source_response.status_code == 200
    assert isinstance(get_source_response.json(), list)
    sources = get_source_response.json()
    source_id = None
    for source in sources:
        if source["database_table_name"] == DATABASE_TABLE_NAME:
            source_id = source["id"]
            assert source["name"] == TEST_SOURCE_NAME
            assert source["type"] == TEST_SOURCE_TYPE
            assert source["database_schema"] == DATABASE_SCHEMA
            assert source["database_table_name"] == DATABASE_TABLE_NAME
        else:
            assert source["name"] != TEST_SOURCE_NAME

    qdrant_service = QdrantService.from_defaults()
    assert qdrant_service.collection_exists(QDRANT_COLLECTION_NAME)

    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    chunk_df = db_service.get_table_df(
        table_name=DATABASE_TABLE_NAME,
        schema_name=DATABASE_SCHEMA,
    )
    assert not chunk_df.empty
    assert "content" in chunk_df.columns
    assert "file_id" in chunk_df.columns

    delete_endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}/{task_id}"
    delete_response = requests.delete(delete_endpoint, headers=HEADERS_JWT)
    assert delete_response.status_code == 204

    delete_source_endpoint = f"{BASE_URL}/sources/{ORGANIZATION_ID}/{source_id}"
    delete_source_response = requests.delete(delete_source_endpoint, headers=HEADERS_JWT)
    assert delete_source_response.status_code == 204

    assert not qdrant_service.collection_exists(QDRANT_COLLECTION_NAME)
    assert not db_service.table_exists(
        table_name=DATABASE_TABLE_NAME,
        schema_name=DATABASE_SCHEMA,
    )
