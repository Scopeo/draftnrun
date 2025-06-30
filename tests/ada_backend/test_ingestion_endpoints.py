import requests

from ada_backend.database.setup_db import SessionLocal
from ada_backend.scripts.get_supabase_token import get_user_jwt
from ada_backend.schemas.ingestion_task_schema import IngestionTaskQueue
from ada_backend.database import models as db
from ada_backend.services.agent_runner_service import get_organization_llm_providers
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from data_ingestion.boto3_client import get_s3_boto3_client, file_exists_in_bucket
from ingestion_script.ingest_folder_source import ingest_dev_local_folder_source, ingest_local_folder_source
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
S3_CLIENT = get_s3_boto3_client()


def test_ingest_local_folder_source():
    test_source_name = "Test_Ingestion_Local_Folder"
    test_source_type = "local"
    test_source_attributes = {"path": "tests/resources/documents/sample.pdf", "access_token": None}
    database_schema, database_table_name, qdrant_collection_name = get_sanitize_names(
        source_name=test_source_name,
        organization_id=ORGANIZATION_ID,
    )

    endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}"
    payload = IngestionTaskQueue(
        source_name=test_source_name,
        source_type=db.SourceType.DEV_LOCAL,
        status=db.TaskStatus.PENDING,
        source_attributes=test_source_attributes,
    )
    response = requests.post(endpoint, headers=HEADERS_JWT, json=payload.model_dump())
    task_id = response.json()

    assert response.status_code == 201
    assert isinstance(task_id, str)
    assert len(task_id) > 0
    set_trace_manager(TraceManager(project_name="Test Ingestion"))
    set_tracing_span(
        project_id="None",
        organization_id=ORGANIZATION_ID,
        organization_llm_providers=get_organization_llm_providers(
            session=SessionLocal(), organization_id=ORGANIZATION_ID
        ),
    )
    ingest_dev_local_folder_source(
        path=test_source_attributes["path"],
        organization_id=ORGANIZATION_ID,
        source_name=test_source_name,
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
        if source["database_table_name"] == database_table_name:
            source_id = source["id"]
            assert source["name"] == test_source_name
            assert source["type"] == test_source_type
            assert source["database_schema"] == database_schema
            assert source["database_table_name"] == database_table_name
        else:
            assert source["name"] != test_source_name

    qdrant_service = QdrantService.from_defaults()
    assert qdrant_service.collection_exists(qdrant_collection_name)

    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    chunk_df = db_service.get_table_df(
        table_name=database_table_name,
        schema_name=database_schema,
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

    assert not qdrant_service.collection_exists(qdrant_collection_name)
    assert not db_service.table_exists(
        table_name=database_table_name,
        schema_name=database_schema,
    )


def test_ingest_remote_local_folder_source():
    test_source_name = "Test_Ingestion_Remote_Folder"
    test_source_type = "remote_local"
    test_source_attributes = {
        "access_token": None,
        "path": "/user/files/",
        "description_remote_folder": [
            {
                "path": "tests/resources/documents/sample.pdf",
                "name": "sample.pdf",
                "s3_path": None,
                "last_edited_ts": "2024-06-01T12:00:00Z",
                "metadata": {"author": "User"},
            }
        ],
        "folder_id": "abc123",
        "source_db_url": None,
        "source_table_name": None,
        "id_column_name": None,
        "text_column_names": None,
        "source_schema_name": None,
        "metadata_column_names": None,
        "timestamp_column_name": None,
        "is_sync_enabled": False,
    }
    database_schema, database_table_name, qdrant_collection_name = get_sanitize_names(
        source_name=test_source_name,
        organization_id=ORGANIZATION_ID,
    )
    endpoint_upload_file = f"{BASE_URL}/files/{ORGANIZATION_ID}/upload"
    with open("tests/resources/documents/sample.pdf", "rb") as f:
        files_payload = [("files", ("doc1.pdf", f, "application/pdf"))]
        response = requests.post(endpoint_upload_file, headers=HEADERS_JWT, files=files_payload)
        assert response.status_code == 200
    list_uploaded_files = response.json()
    assert len(list_uploaded_files) == 1
    sanitized_file_name = list_uploaded_files[0]["s3_sanitized_name"]

    assert file_exists_in_bucket(s3_client=S3_CLIENT, bucket_name=settings.S3_BUCKET_NAME, key=sanitized_file_name)
    test_source_attributes["description_remote_folder"][0]["s3_path"] = sanitized_file_name

    endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}"
    payload = IngestionTaskQueue(
        source_name=test_source_name,
        source_type=db.SourceType.LOCAL,
        status=db.TaskStatus.PENDING,
        source_attributes=test_source_attributes,
    )
    response = requests.post(endpoint, headers=HEADERS_JWT, json=payload.model_dump())
    task_id = response.json()

    assert response.status_code == 201
    assert isinstance(task_id, str)
    assert len(task_id) > 0

    ingest_local_folder_source(
        description_local_folder=test_source_attributes["description_remote_folder"],
        organization_id=ORGANIZATION_ID,
        source_name=test_source_name,
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
        if source["database_table_name"] == database_table_name:
            source_id = source["id"]
            assert source["name"] == test_source_name
            assert source["type"] == test_source_type
            assert source["database_schema"] == database_schema
            assert source["database_table_name"] == database_table_name
        else:
            assert source["name"] != test_source_name

    qdrant_service = QdrantService.from_defaults()
    assert qdrant_service.collection_exists(qdrant_collection_name)

    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    chunk_df = db_service.get_table_df(
        table_name=database_table_name,
        schema_name=database_schema,
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

    assert not qdrant_service.collection_exists(qdrant_collection_name)
    assert not db_service.table_exists(
        table_name=database_table_name,
        schema_name=database_schema,
    )

    assert not file_exists_in_bucket(s3_client=S3_CLIENT, bucket_name=settings.S3_BUCKET_NAME, key=sanitized_file_name)
