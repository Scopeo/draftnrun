import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from ada_backend.database import models as db
from ada_backend.database.setup_db import SessionLocal
from ada_backend.main import app
from ada_backend.schemas.ingestion_task_schema import IngestionTaskQueue
from ada_backend.scripts.get_supabase_token import get_user_jwt
from ada_backend.services.agent_runner_service import get_organization_llm_providers
from data_ingestion.boto3_client import file_exists_in_bucket, get_s3_boto3_client
from engine.storage_service.local_service import SQLLocalService
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from ingestion_script.ingest_folder_source import ingest_local_folder_source
from ingestion_script.utils import get_sanitize_names
from settings import settings

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
S3_CLIENT = get_s3_boto3_client()


def test_ingest_local_folder_source():
    test_source_name = "Test_Ingestion_Local_Folder"
    test_source_type = "local"
    test_source_attributes = {
        "access_token": None,
        "path": "/user/files/",
        "list_of_files_from_local_folder": [
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
    test_source_id = str(uuid.uuid4())
    database_schema, database_table_name, qdrant_collection_name = get_sanitize_names(
        organization_id=ORGANIZATION_ID,
        source_id=test_source_id,
    )

    with open("tests/resources/documents/sample.pdf", "rb") as f:
        files_payload = [("files", ("doc1.pdf", f, "application/pdf"))]
        response = client.post(f"/files/{ORGANIZATION_ID}/upload", headers=HEADERS_JWT, files=files_payload)
        assert response.status_code == 200
    list_uploaded_files = response.json()
    assert len(list_uploaded_files) == 1
    sanitized_file_name = list_uploaded_files[0]["s3_path_file"]

    assert file_exists_in_bucket(s3_client=S3_CLIENT, bucket_name=settings.S3_BUCKET_NAME, key=sanitized_file_name)
    test_source_attributes["list_of_files_from_local_folder"][0]["s3_path"] = sanitized_file_name

    payload = IngestionTaskQueue(
        source_name=test_source_name,
        source_type=db.SourceType.LOCAL,
        status=db.TaskStatus.PENDING,
        source_attributes=test_source_attributes,
    )
    response = client.post(f"/ingestion_task/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=payload.model_dump())
    task_id = response.json()

    assert response.status_code == 201
    assert isinstance(task_id, str)
    assert len(task_id) > 0
    set_trace_manager(TraceManager(project_name="Test Ingestion"))
    session = SessionLocal()
    try:
        organization_llm_providers = get_organization_llm_providers(session=session, organization_id=ORGANIZATION_ID)
    finally:
        session.close()

    set_tracing_span(
        project_id="None",
        organization_id=ORGANIZATION_ID,
        organization_llm_providers=organization_llm_providers,
    )

    # Mock create_source and update_ingestion_task to use test client instead of making HTTP requests
    def mock_create_source(organization_id: str, source_data):
        response = client.post(
            f"/sources/{organization_id}",
            json=source_data.model_dump(mode="json"),
            headers=HEADERS_API_KEY,
        )
        response.raise_for_status()
        return response.json()

    def mock_update_ingestion_task(organization_id: str, ingestion_task):
        response = client.patch(
            f"/ingestion_task/{organization_id}",
            json=ingestion_task.model_dump(mode="json"),
            headers=HEADERS_API_KEY,
        )
        response.raise_for_status()

    mock_qdrant_instance = MagicMock()
    mock_qdrant_instance.collection_exists = MagicMock(return_value=True)
    mock_qdrant_instance.collection_exists_async = AsyncMock(return_value=False)  # Collection doesn't exist initially
    mock_qdrant_instance.create_collection_async = AsyncMock()
    mock_qdrant_instance.sync_df_with_collection_async = AsyncMock()

    with (
        patch("ingestion_script.ingest_folder_source.create_source", side_effect=mock_create_source),
        patch("ingestion_script.ingest_folder_source.update_ingestion_task", side_effect=mock_update_ingestion_task),
        patch("ingestion_script.ingest_folder_source.QdrantService") as mock_qdrant_service_class,
    ):
        mock_qdrant_service_class.from_defaults.return_value = mock_qdrant_instance
        asyncio.run(
            ingest_local_folder_source(
                list_of_files_to_ingest=test_source_attributes["list_of_files_from_local_folder"],
                organization_id=ORGANIZATION_ID,
                source_id=test_source_id,
                source_name=test_source_name,
                task_id=task_id,
                save_supabase=False,
                add_doc_description_to_chunks=False,
            )
        )

    get_source_response = client.get(
        f"/sources/{ORGANIZATION_ID}",
        headers=HEADERS_JWT,
    )
    assert get_source_response.status_code == 200
    assert isinstance(get_source_response.json(), list)
    sources = get_source_response.json()
    found_source = False
    for source in sources:
        if source["id"] == test_source_id:
            assert source["name"] == test_source_name
            assert source["type"] == test_source_type
            assert source["database_schema"] == database_schema
            assert source["database_table_name"] == database_table_name
            assert source["qdrant_collection_name"] == qdrant_collection_name
            found_source = True
            break
    assert found_source

    # Verify Qdrant operations were called correctly
    mock_qdrant_instance.sync_df_with_collection_async.assert_called_once()
    mock_qdrant_instance.create_collection_async.assert_called_once()

    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    chunk_df = db_service.get_table_df(
        table_name=database_table_name,
        schema_name=database_schema,
    )
    assert not chunk_df.empty
    assert "content" in chunk_df.columns
    assert "file_id" in chunk_df.columns

    delete_response = client.delete(f"/ingestion_task/{ORGANIZATION_ID}/{task_id}", headers=HEADERS_JWT)
    assert delete_response.status_code == 204

    delete_source_response = client.delete(f"/sources/{ORGANIZATION_ID}/{test_source_id}", headers=HEADERS_JWT)
    assert delete_source_response.status_code == 204

    assert not db_service.table_exists(
        table_name=database_table_name,
        schema_name=database_schema,
    )

    assert not file_exists_in_bucket(s3_client=S3_CLIENT, bucket_name=settings.S3_BUCKET_NAME, key=sanitized_file_name)
