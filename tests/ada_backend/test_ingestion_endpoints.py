import requests
import uuid

from ada_backend.database.setup_db import SessionLocal
from ada_backend.scripts.get_supabase_token import get_user_jwt
from ada_backend.schemas.ingestion_task_schema import IngestionTaskQueue
from ada_backend.database import models as db
from ada_backend.services.agent_runner_service import get_organization_llm_providers
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from data_ingestion.boto3_client import get_s3_boto3_client, file_exists_in_bucket
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
S3_CLIENT = get_s3_boto3_client()


def test_ingest_local_folder_source():
    test_source_name = f"Test_Ingestion_Local_Folder_{uuid.uuid4().hex[:8]}"
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
    sanitized_file_name = list_uploaded_files[0]["s3_path_file"]

    assert file_exists_in_bucket(s3_client=S3_CLIENT, bucket_name=settings.S3_BUCKET_NAME, key=sanitized_file_name)
    test_source_attributes["list_of_files_from_local_folder"][0]["s3_path"] = sanitized_file_name

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
    set_trace_manager(TraceManager(project_name="Test Ingestion"))
    set_tracing_span(
        project_id="None",
        organization_id=ORGANIZATION_ID,
        organization_llm_providers=get_organization_llm_providers(
            session=SessionLocal(), organization_id=ORGANIZATION_ID
        ),
    )

    ingest_local_folder_source(
        list_of_files_to_ingest=test_source_attributes["list_of_files_from_local_folder"],
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


def test_ingestion_duplicate_source_name_error():
    """Test that ingestion fails when trying to create a source with a name that already exists."""
    test_source_name = f"Test_Duplicate_Source_Name_{uuid.uuid4().hex[:8]}"
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

    # First, create a source with the test name
    endpoint_upload_file = f"{BASE_URL}/files/{ORGANIZATION_ID}/upload"
    with open("tests/resources/documents/sample.pdf", "rb") as f:
        files_payload = [("files", ("doc1.pdf", f, "application/pdf"))]
        response = requests.post(endpoint_upload_file, headers=HEADERS_JWT, files=files_payload)
        assert response.status_code == 200

    list_uploaded_files = response.json()
    sanitized_file_name = list_uploaded_files[0]["s3_path_file"]
    test_source_attributes["list_of_files_from_local_folder"][0]["s3_path"] = sanitized_file_name

    # Create first ingestion task
    endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}"
    payload = IngestionTaskQueue(
        source_name=test_source_name,
        source_type=db.SourceType.LOCAL,
        status=db.TaskStatus.PENDING,
        source_attributes=test_source_attributes,
    )
    response = requests.post(endpoint, headers=HEADERS_JWT, json=payload.model_dump())
    task_id_1 = response.json()
    assert response.status_code == 201

    # Run first ingestion
    set_trace_manager(TraceManager(project_name="Test Ingestion"))
    set_tracing_span(
        project_id="None",
        organization_id=ORGANIZATION_ID,
        organization_llm_providers=get_organization_llm_providers(
            session=SessionLocal(), organization_id=ORGANIZATION_ID
        ),
    )

    ingest_local_folder_source(
        list_of_files_to_ingest=test_source_attributes["list_of_files_from_local_folder"],
        organization_id=ORGANIZATION_ID,
        source_name=test_source_name,
        task_id=task_id_1,
        save_supabase=False,
        add_doc_description_to_chunks=False,
    )

    # Verify first source was created
    sources_response = requests.get(f"{BASE_URL}/sources/{ORGANIZATION_ID}", headers=HEADERS_JWT)
    assert sources_response.status_code == 200
    sources = sources_response.json()
    first_source = None
    for source in sources:
        if source["name"] == test_source_name:
            first_source = source
            break
    assert first_source is not None
    first_source_id = first_source["id"]
    first_created_at = first_source["created_at"]
    first_updated_at = first_source["updated_at"]

    # Now try to create another source with the same name - this should fail with 400
    endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}"
    payload = IngestionTaskQueue(
        source_name=test_source_name,
        source_type=db.SourceType.LOCAL,
        status=db.TaskStatus.PENDING,
        source_attributes=test_source_attributes,
    )
    response = requests.post(endpoint, headers=HEADERS_JWT, json=payload.model_dump())
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]

    # Verify no duplicate was created
    sources_response = requests.get(f"{BASE_URL}/sources/{ORGANIZATION_ID}", headers=HEADERS_JWT)
    assert sources_response.status_code == 200
    sources = sources_response.json()

    # Count sources with the same name
    sources_with_name = [s for s in sources if s["name"] == test_source_name]
    assert (
        len(sources_with_name) == 1
    ), f"Expected 1 source with name {test_source_name}, found {len(sources_with_name)}"

    # Verify the original source is unchanged
    updated_source = sources_with_name[0]
    assert updated_source["id"] == first_source_id, "Source ID should remain the same"
    assert updated_source["created_at"] == first_created_at, "Created timestamp should remain the same"
    assert updated_source["updated_at"] == first_updated_at, "Updated timestamp should remain the same"

    # Clean up
    delete_endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}/{task_id_1}"
    delete_response = requests.delete(delete_endpoint, headers=HEADERS_JWT)
    assert delete_response.status_code == 204

    delete_source_endpoint = f"{BASE_URL}/sources/{ORGANIZATION_ID}/{first_source_id}"
    delete_source_response = requests.delete(delete_source_endpoint, headers=HEADERS_JWT)
    assert delete_source_response.status_code == 204


def test_ingestion_source_update_without_duplicate():
    """Test that updating an existing source works correctly without creating duplicates."""
    test_source_name = f"Test_Update_Source_No_Duplicate_{uuid.uuid4().hex[:8]}"
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

    # Upload file for first ingestion
    endpoint_upload_file = f"{BASE_URL}/files/{ORGANIZATION_ID}/upload"
    with open("tests/resources/documents/sample.pdf", "rb") as f:
        files_payload = [("files", ("doc1.pdf", f, "application/pdf"))]
        response = requests.post(endpoint_upload_file, headers=HEADERS_JWT, files=files_payload)
        assert response.status_code == 200

    list_uploaded_files = response.json()
    sanitized_file_name = list_uploaded_files[0]["s3_path_file"]
    test_source_attributes["list_of_files_from_local_folder"][0]["s3_path"] = sanitized_file_name

    # Create and run first ingestion
    endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}"
    payload = IngestionTaskQueue(
        source_name=test_source_name,
        source_type=db.SourceType.LOCAL,
        status=db.TaskStatus.PENDING,
        source_attributes=test_source_attributes,
    )
    response = requests.post(endpoint, headers=HEADERS_JWT, json=payload.model_dump())
    task_id_1 = response.json()
    assert response.status_code == 201

    # Check initial status of first task by getting all tasks and filtering
    tasks_response = requests.get(f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}", headers=HEADERS_JWT)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()
    first_task = None
    for task in tasks:
        if task["id"] == task_id_1:
            first_task = task
            break
    assert first_task is not None
    assert first_task["status"] == "pending"

    set_trace_manager(TraceManager(project_name="Test Ingestion"))
    set_tracing_span(
        project_id="None",
        organization_id=ORGANIZATION_ID,
        organization_llm_providers=get_organization_llm_providers(
            session=SessionLocal(), organization_id=ORGANIZATION_ID
        ),
    )

    ingest_local_folder_source(
        list_of_files_to_ingest=test_source_attributes["list_of_files_from_local_folder"],
        organization_id=ORGANIZATION_ID,
        source_name=test_source_name,
        task_id=task_id_1,
        save_supabase=False,
        add_doc_description_to_chunks=False,
    )

    # Check final status of first task
    tasks_response = requests.get(f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}", headers=HEADERS_JWT)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()
    first_task = None
    for task in tasks:
        if task["id"] == task_id_1:
            first_task = task
            break
    assert first_task is not None
    assert first_task["status"] == "completed"
    assert first_task["source_id"] is not None

    # Get the created source
    sources_response = requests.get(f"{BASE_URL}/sources/{ORGANIZATION_ID}", headers=HEADERS_JWT)
    assert sources_response.status_code == 200
    sources = sources_response.json()
    original_source = None
    for source in sources:
        if source["name"] == test_source_name:
            original_source = source
            break
    assert original_source is not None
    original_source_id = original_source["id"]
    original_created_at = original_source["created_at"]
    original_updated_at = original_source["updated_at"]
    original_last_ingestion_time = original_source.get("last_ingestion_time")

    # Wait a moment to ensure timestamps will be different
    import time

    time.sleep(1)

    # Upload file again for the update ingestion (since the first one was cleaned up)
    endpoint_upload_file = f"{BASE_URL}/files/{ORGANIZATION_ID}/upload"
    with open("tests/resources/documents/sample.pdf", "rb") as f:
        files_payload = [("files", ("doc2.pdf", f, "application/pdf"))]
        response = requests.post(endpoint_upload_file, headers=HEADERS_JWT, files=files_payload)
        assert response.status_code == 200

    list_uploaded_files = response.json()
    sanitized_file_name_2 = list_uploaded_files[0]["s3_path_file"]
    update_source_attributes = test_source_attributes.copy()
    update_source_attributes["list_of_files_from_local_folder"][0]["s3_path"] = sanitized_file_name_2

    # Now use the update_by_source endpoint to update the existing source
    update_endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}/update_by_source"
    update_payload = {
        "source_id": original_source_id,
        "source_type": db.SourceType.LOCAL,
        "status": db.TaskStatus.PENDING,
        "source_attributes": update_source_attributes,
    }
    response = requests.patch(update_endpoint, headers=HEADERS_JWT, json=update_payload)
    assert response.status_code == 200
    update_result = response.json()
    task_id_2 = update_result["task_id"]

    # Check initial status of second task
    tasks_response = requests.get(f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}", headers=HEADERS_JWT)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()
    second_task = None
    for task in tasks:
        if task["id"] == task_id_2:
            second_task = task
            break
    assert second_task is not None
    assert second_task["status"] == "pending"

    # Run the update ingestion
    # The ingestion script will detect that the source already exists and update it
    # This is the expected behavior for updates
    ingest_local_folder_source(
        list_of_files_to_ingest=update_source_attributes["list_of_files_from_local_folder"],
        organization_id=ORGANIZATION_ID,
        source_name=test_source_name,
        task_id=task_id_2,
        save_supabase=False,
        add_doc_description_to_chunks=False,
    )

    # Check final status of second task
    tasks_response = requests.get(f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}", headers=HEADERS_JWT)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()
    second_task = None
    for task in tasks:
        if task["id"] == task_id_2:
            second_task = task
            break
    assert second_task is not None
    # The task should complete successfully and have status "completed"
    assert second_task["status"] == "completed", f"Expected completed, got {second_task['status']}"
    assert second_task["source_id"] == original_source_id, "Second task should reference the same source ID"

    # Verify the source was updated correctly
    sources_response = requests.get(f"{BASE_URL}/sources/{ORGANIZATION_ID}", headers=HEADERS_JWT)
    assert sources_response.status_code == 200
    sources = sources_response.json()

    # Should still be only one source with this name
    sources_with_name = [s for s in sources if s["name"] == test_source_name]
    assert (
        len(sources_with_name) == 1
    ), f"Expected 1 source with name {test_source_name}, found {len(sources_with_name)}"

    updated_source = sources_with_name[0]

    # Verify the source was updated, not recreated
    assert updated_source["id"] == original_source_id, "Source ID should remain the same"
    assert updated_source["created_at"] == original_created_at, "Created timestamp should remain the same"
    assert updated_source["updated_at"] != original_updated_at, "Updated timestamp should have changed"

    # Verify last_ingestion_time was set and is newer
    # Note: last_ingestion_time might not be present in all responses, so we check if it exists
    if "last_ingestion_time" in updated_source:
        assert updated_source["last_ingestion_time"] is not None, "Last ingestion timestamp should be set"
        if original_last_ingestion_time:
            assert (
                updated_source["last_ingestion_time"] != original_last_ingestion_time
            ), "Last ingestion timestamp should have changed"
    else:
        # If last_ingestion_time is not in the response, we can still verify the update worked
        # by checking that updated_at has changed
        assert updated_source["updated_at"] != original_updated_at, "Updated timestamp should have changed"

    # Verify the source has the expected fields
    expected_fields = [
        "id",
        "name",
        "type",
        "database_schema",
        "database_table_name",
        "qdrant_collection_name",
        "qdrant_schema",
        "embedding_model_reference",
        "created_at",
        "updated_at",
        "last_ingestion_time",
    ]
    for field in expected_fields:
        assert field in updated_source, f"Source should have field: {field}"

    # Clean up
    delete_endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}/{task_id_1}"
    delete_response = requests.delete(delete_endpoint, headers=HEADERS_JWT)
    assert delete_response.status_code == 204

    delete_endpoint = f"{BASE_URL}/ingestion_task/{ORGANIZATION_ID}/{task_id_2}"
    delete_response = requests.delete(delete_endpoint, headers=HEADERS_JWT)
    assert delete_response.status_code == 204

    delete_source_endpoint = f"{BASE_URL}/sources/{ORGANIZATION_ID}/{original_source_id}"
    delete_source_response = requests.delete(delete_source_endpoint, headers=HEADERS_JWT)
    assert delete_source_response.status_code == 204
