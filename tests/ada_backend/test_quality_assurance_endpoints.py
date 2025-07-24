from uuid import uuid4
from fastapi.testclient import TestClient

from ada_backend.main import app
from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings

client = TestClient(app)
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"  # umbrella organization
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}

# Use an existing project ID from the seed data
TEST_PROJECT_ID = "f7ddbfcb-6843-4ae9-a15b-40aa565b955b"  # graph_test_project


def test_create_single_input_groundtruth():
    """Test creating a single input-groundtruth entry."""
    # First create a dataset
    dataset_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/datasets"
    dataset_payload = {"datasets": ["test_dataset"]}
    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]
    
    # Now create input-groundtruth entry
    endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}"
    payload = {"inputs_groundtruths": [{"input": "What is the capital of France?", "groundtruth": "Paris"}]}

    response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    input_groundtruth = response.json()

    assert response.status_code == 200
    assert isinstance(input_groundtruth, dict)
    assert "inputs_groundtruths" in input_groundtruth
    assert len(input_groundtruth["inputs_groundtruths"]) == 1
    
    created_ig = input_groundtruth["inputs_groundtruths"][0]
    assert "id" in created_ig
    assert created_ig["input"] == "What is the capital of France?"
    assert created_ig["groundtruth"] == "Paris"
    assert created_ig["dataset_id"] == dataset_id
    assert created_ig["created_at"] is not None
    assert created_ig["updated_at"] is not None

    # Clean up - delete the created entry
    input_groundtruth_id = created_ig["id"]
    delete_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{input_groundtruth_id}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)
    
    # Clean up dataset
    client.delete(f"/projects/{TEST_PROJECT_ID}/qa/datasets/{dataset_id}", headers=HEADERS_JWT)


def test_create_multiple_inputs_groundtruths():
    """Test creating multiple input-groundtruth entries."""
    # First create a dataset
    dataset_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/datasets"
    dataset_payload = {"datasets": ["test_dataset_multiple"]}
    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]
    
    endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}"
    payload = {
        "inputs_groundtruths": [
            {"input": "What is 2 + 2?", "groundtruth": "4"},
            {"input": "Who wrote Romeo and Juliet?", "groundtruth": "William Shakespeare"},
            {"input": "What is the largest planet in our solar system?", "groundtruth": "Jupiter"},
        ]
    }

    response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    inputs_groundtruths = response.json()

    assert response.status_code == 200
    assert isinstance(inputs_groundtruths, dict)
    assert "inputs_groundtruths" in inputs_groundtruths
    assert isinstance(inputs_groundtruths["inputs_groundtruths"], list)
    assert len(inputs_groundtruths["inputs_groundtruths"]) == 3

    # Verify each input-groundtruth entry
    for ig in inputs_groundtruths["inputs_groundtruths"]:
        assert "id" in ig
        assert "input" in ig
        assert "groundtruth" in ig
        assert "dataset_id" in ig
        assert "created_at" in ig
        assert "updated_at" in ig
        assert ig["dataset_id"] == dataset_id

    # Clean up - delete all created entries
    for ig in inputs_groundtruths["inputs_groundtruths"]:
        delete_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{ig['id']}"
        client.delete(delete_endpoint, headers=HEADERS_JWT)
    
    # Clean up dataset
    client.delete(f"/projects/{TEST_PROJECT_ID}/qa/datasets/{dataset_id}", headers=HEADERS_JWT)


def test_get_inputs_groundtruths_by_dataset():
    """Test getting input-groundtruth entries with pagination."""
    # First create a dataset
    dataset_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/datasets"
    dataset_payload = {"datasets": ["test_dataset_pagination"]}
    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]
    
    # Create some test data
    endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}"
    payload = {"inputs_groundtruths": [{"input": "Test input for pagination", "groundtruth": "Test groundtruth for pagination"}]}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_ig = create_response.json()["inputs_groundtruths"][0]

    # Now test getting the list
    response = client.get(endpoint, headers=HEADERS_JWT)
    inputs_groundtruths = response.json()

    assert response.status_code == 200
    assert isinstance(inputs_groundtruths, list)
    assert len(inputs_groundtruths) >= 1  # At least the one we created

    # Verify each input-groundtruth entry
    for ig in inputs_groundtruths:
        assert "input_id" in ig
        assert "input" in ig
        assert "groundtruth" in ig
        assert "output" in ig
        assert "version_id" in ig
        assert "version" in ig

    # Clean up - delete the created entry
    delete_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{created_ig['id']}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)
    
    # Clean up dataset
    client.delete(f"/projects/{TEST_PROJECT_ID}/qa/datasets/{dataset_id}", headers=HEADERS_JWT)


def test_get_inputs_groundtruths_with_pagination():
    """Test getting input-groundtruth entries with pagination parameters."""
    # First create a dataset
    dataset_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/datasets"
    dataset_payload = {"datasets": ["test_dataset_pagination_params"]}
    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]
    
    # Create some test data
    endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}"
    payload = {"inputs_groundtruths": [{"input": "Test input for pagination params", "groundtruth": "Test groundtruth for pagination params"}]}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_ig = create_response.json()["inputs_groundtruths"][0]

    # Test with pagination parameters
    response = client.get(f"{endpoint}?page=1&size=10", headers=HEADERS_JWT)
    inputs_groundtruths = response.json()

    assert response.status_code == 200
    assert isinstance(inputs_groundtruths, list)

    # Clean up - delete the created entry
    delete_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{created_ig['id']}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)
    
    # Clean up dataset
    client.delete(f"/projects/{TEST_PROJECT_ID}/qa/datasets/{dataset_id}", headers=HEADERS_JWT)


def test_get_input_groundtruth_by_id():
    """Test getting a specific input-groundtruth entry by ID."""
    # First create a dataset
    dataset_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/datasets"
    dataset_payload = {"datasets": ["test_dataset_by_id"]}
    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]
    
    # Create test data
    endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}"
    payload = {"inputs_groundtruths": [{"input": "Test input by ID", "groundtruth": "Test groundtruth by ID"}]}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_ig = create_response.json()["inputs_groundtruths"][0]
    input_groundtruth_id = created_ig["id"]

    # Get the specific entry
    get_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{input_groundtruth_id}"
    response = client.get(get_endpoint, headers=HEADERS_JWT)
    input_groundtruth = response.json()

    assert response.status_code == 200
    assert isinstance(input_groundtruth, dict)
    assert input_groundtruth["id"] == input_groundtruth_id
    assert input_groundtruth["input"] == "Test input by ID"
    assert input_groundtruth["groundtruth"] == "Test groundtruth by ID"
    assert input_groundtruth["dataset_id"] == dataset_id

    # Clean up - delete the created entry
    delete_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{input_groundtruth_id}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)
    
    # Clean up dataset
    client.delete(f"/projects/{TEST_PROJECT_ID}/qa/datasets/{dataset_id}", headers=HEADERS_JWT)


def test_create_input_groundtruth_without_groundtruth():
    """Test creating an input-groundtruth entry without groundtruth (optional field)."""
    # First create a dataset
    dataset_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/datasets"
    dataset_payload = {"datasets": ["test_dataset_no_groundtruth"]}
    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]
    
    endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}"
    payload = {"inputs_groundtruths": [{"input": "What is the weather like today?"}]}

    response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    input_groundtruth = response.json()

    assert response.status_code == 200
    assert isinstance(input_groundtruth, dict)
    assert "inputs_groundtruths" in input_groundtruth
    assert len(input_groundtruth["inputs_groundtruths"]) == 1
    
    created_ig = input_groundtruth["inputs_groundtruths"][0]
    assert created_ig["input"] == "What is the weather like today?"
    assert created_ig["groundtruth"] is None

    # Clean up - delete the created entry
    delete_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{created_ig['id']}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)
    
    # Clean up dataset
    client.delete(f"/projects/{TEST_PROJECT_ID}/qa/datasets/{dataset_id}", headers=HEADERS_JWT)


def test_update_input_groundtruth():
    """Test updating an input-groundtruth entry."""
    # First create a dataset
    dataset_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/datasets"
    dataset_payload = {"datasets": ["test_dataset_update"]}
    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]
    
    # Create test data
    endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}"
    payload = {"inputs_groundtruths": [{"input": "Original input", "groundtruth": "Original groundtruth"}]}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_ig = create_response.json()["inputs_groundtruths"][0]
    input_groundtruth_id = created_ig["id"]

    # Update the entry
    update_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{input_groundtruth_id}"
    update_payload = {"input": "Updated input", "groundtruth": "Updated groundtruth"}
    response = client.put(update_endpoint, headers=HEADERS_JWT, json=update_payload)
    updated_ig = response.json()

    assert response.status_code == 200
    assert updated_ig["input"] == "Updated input"
    assert updated_ig["groundtruth"] == "Updated groundtruth"
    assert updated_ig["id"] == input_groundtruth_id

    # Clean up - delete the created entry
    delete_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{input_groundtruth_id}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)
    
    # Clean up dataset
    client.delete(f"/projects/{TEST_PROJECT_ID}/qa/datasets/{dataset_id}", headers=HEADERS_JWT)


def test_update_input_groundtruth_partial():
    """Test partially updating an input-groundtruth entry (only some fields)."""
    # First create a dataset
    dataset_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/datasets"
    dataset_payload = {"datasets": ["test_dataset_partial_update"]}
    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]
    
    # Create test data
    endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}"
    payload = {"inputs_groundtruths": [{"input": "Original input", "groundtruth": "Original groundtruth"}]}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_ig = create_response.json()["inputs_groundtruths"][0]
    input_groundtruth_id = created_ig["id"]

    # Partially update the entry (only input)
    update_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{input_groundtruth_id}"
    update_payload = {"input": "Partially updated input"}
    response = client.put(update_endpoint, headers=HEADERS_JWT, json=update_payload)
    updated_ig = response.json()

    assert response.status_code == 200
    assert updated_ig["input"] == "Partially updated input"
    assert updated_ig["groundtruth"] == "Original groundtruth"  # Should remain unchanged
    assert updated_ig["id"] == input_groundtruth_id

    # Clean up - delete the created entry
    delete_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{input_groundtruth_id}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)
    
    # Clean up dataset
    client.delete(f"/projects/{TEST_PROJECT_ID}/qa/datasets/{dataset_id}", headers=HEADERS_JWT)


def test_delete_input_groundtruth():
    """Test deleting an input-groundtruth entry."""
    # First create a dataset
    dataset_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/datasets"
    dataset_payload = {"datasets": ["test_dataset_delete"]}
    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]
    
    # Create test data
    endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}"
    payload = {"inputs_groundtruths": [{"input": "Input to delete", "groundtruth": "Groundtruth to delete"}]}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_ig = create_response.json()["inputs_groundtruths"][0]
    input_groundtruth_id = created_ig["id"]

    # Delete the entry
    delete_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{input_groundtruth_id}"
    response = client.delete(delete_endpoint, headers=HEADERS_JWT)

    assert response.status_code == 200
    assert response.json()["message"] == f"Input-groundtruth entry {input_groundtruth_id} deleted successfully"

    # Verify the entry is deleted
    get_endpoint = f"/projects/{TEST_PROJECT_ID}/qa/{dataset_id}/{input_groundtruth_id}"
    get_response = client.get(get_endpoint, headers=HEADERS_JWT)
    assert get_response.status_code == 404
    
    # Clean up dataset
    client.delete(f"/projects/{TEST_PROJECT_ID}/qa/datasets/{dataset_id}", headers=HEADERS_JWT)
