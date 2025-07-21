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


def test_create_single_question_answer():
    """Test creating a single question-answer entry."""
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}"
    payload = {"question": "What is the capital of France?", "groundtruth": "Paris"}

    response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    question_answer = response.json()

    assert response.status_code == 200
    assert isinstance(question_answer, dict)
    assert "id" in question_answer
    assert question_answer["question"] == "What is the capital of France?"
    assert question_answer["groundtruth"] == "Paris"
    assert question_answer["organization_id"] == ORGANIZATION_ID
    assert question_answer["project_id"] == TEST_PROJECT_ID
    assert question_answer["created_at"] is not None
    assert question_answer["updated_at"] is not None

    # Clean up - delete the created entry
    question_answer_id = question_answer["id"]
    delete_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{question_answer_id}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)


def test_create_multiple_question_answers():
    """Test creating multiple question-answer entries."""
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/list"
    payload = {
        "questions_answers": [
            {"question": "What is 2 + 2?", "groundtruth": "4"},
            {"question": "Who wrote Romeo and Juliet?", "groundtruth": "William Shakespeare"},
            {"question": "What is the largest planet in our solar system?", "groundtruth": "Jupiter"},
        ]
    }

    response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    question_answers = response.json()

    assert response.status_code == 200
    assert isinstance(question_answers, dict)
    assert "questions_answers" in question_answers
    assert isinstance(question_answers["questions_answers"], list)
    assert len(question_answers["questions_answers"]) == 3

    # Verify each question-answer entry
    for qa in question_answers["questions_answers"]:
        assert "id" in qa
        assert "question" in qa
        assert "groundtruth" in qa
        assert "organization_id" in qa
        assert "project_id" in qa
        assert "created_at" in qa
        assert "updated_at" in qa
        assert qa["organization_id"] == ORGANIZATION_ID
        assert qa["project_id"] == TEST_PROJECT_ID

    # Clean up - delete all created entries
    for qa in question_answers["questions_answers"]:
        delete_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{qa['id']}"
        client.delete(delete_endpoint, headers=HEADERS_JWT)


def test_get_question_answers_by_organization_and_project():
    """Test getting question-answer entries with pagination."""
    # First create some test data
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}"
    payload = {"question": "Test question for pagination", "groundtruth": "Test answer for pagination"}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_qa = create_response.json()

    # Now test getting the list
    response = client.get(endpoint, headers=HEADERS_JWT)
    question_answers = response.json()

    assert response.status_code == 200
    assert isinstance(question_answers, list)
    assert len(question_answers) >= 1  # At least the one we created

    # Verify each question-answer entry
    for qa in question_answers:
        assert "id" in qa
        assert "question" in qa
        assert "groundtruth" in qa
        assert "organization_id" in qa
        assert "project_id" in qa
        assert "created_at" in qa
        assert "updated_at" in qa
        assert qa["organization_id"] == ORGANIZATION_ID
        assert qa["project_id"] == TEST_PROJECT_ID

    # Clean up
    delete_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{created_qa['id']}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)


def test_get_question_answers_with_pagination():
    """Test getting question-answer entries with specific pagination parameters."""
    # First create some test data
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}"
    test_entries = []

    for i in range(3):
        payload = {"question": f"Test question {i}", "groundtruth": f"Test answer {i}"}
        response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
        assert response.status_code == 200
        test_entries.append(response.json())

    # Test pagination
    params = {"page": 1, "size": 2}
    response = client.get(endpoint, headers=HEADERS_JWT, params=params)
    question_answers = response.json()

    assert response.status_code == 200
    assert isinstance(question_answers, list)
    assert len(question_answers) <= 2  # Should be limited by size parameter

    # Clean up
    for qa in test_entries:
        delete_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{qa['id']}"
        client.delete(delete_endpoint, headers=HEADERS_JWT)


def test_get_question_answer_by_id():
    """Test getting a specific question-answer entry by ID."""
    # First create a test entry
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}"
    payload = {"question": "What is the capital of France?", "groundtruth": "Paris"}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_qa = create_response.json()
    question_answer_id = created_qa["id"]

    # Test getting by ID
    get_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{question_answer_id}"
    response = client.get(get_endpoint, headers=HEADERS_JWT)
    question_answer = response.json()

    assert response.status_code == 200
    assert isinstance(question_answer, dict)
    assert question_answer["id"] == question_answer_id
    assert question_answer["question"] == "What is the capital of France?"
    assert question_answer["groundtruth"] == "Paris"
    assert question_answer["organization_id"] == ORGANIZATION_ID
    assert question_answer["project_id"] == TEST_PROJECT_ID

    # Clean up
    delete_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{question_answer_id}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)


def test_get_nonexistent_question_answer():
    """Test getting a question-answer entry that doesn't exist."""
    nonexistent_id = str(uuid4())
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{nonexistent_id}"
    response = client.get(endpoint, headers=HEADERS_JWT)

    assert response.status_code == 404


def test_update_question_answer():
    """Test updating a question-answer entry."""
    # First create a test entry
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}"
    payload = {"question": "Original question", "groundtruth": "Original answer"}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_qa = create_response.json()
    question_answer_id = created_qa["id"]

    # Test updating
    update_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{question_answer_id}"
    update_payload = {"question": "Updated question", "groundtruth": "Updated answer"}

    response = client.put(update_endpoint, headers=HEADERS_JWT, json=update_payload)
    question_answer = response.json()

    assert response.status_code == 200
    assert isinstance(question_answer, dict)
    assert question_answer["id"] == question_answer_id
    assert question_answer["question"] == "Updated question"
    assert question_answer["groundtruth"] == "Updated answer"
    assert question_answer["organization_id"] == ORGANIZATION_ID
    assert question_answer["project_id"] == TEST_PROJECT_ID

    # Clean up
    delete_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{question_answer_id}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)


def test_update_question_answer_partial():
    """Test updating a question-answer entry with partial data."""
    # First create a test entry
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}"
    payload = {"question": "Original question", "groundtruth": "Original answer"}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_qa = create_response.json()
    question_answer_id = created_qa["id"]

    # Test partial update
    update_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{question_answer_id}"
    update_payload = {"question": "Partially updated question"}

    response = client.put(update_endpoint, headers=HEADERS_JWT, json=update_payload)
    question_answer = response.json()

    assert response.status_code == 200
    assert isinstance(question_answer, dict)
    assert question_answer["id"] == question_answer_id
    assert question_answer["question"] == "Partially updated question"
    assert question_answer["groundtruth"] == "Original answer"  # Should remain unchanged
    assert question_answer["organization_id"] == ORGANIZATION_ID
    assert question_answer["project_id"] == TEST_PROJECT_ID

    # Clean up
    delete_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{question_answer_id}"
    client.delete(delete_endpoint, headers=HEADERS_JWT)


def test_update_nonexistent_question_answer():
    """Test updating a question-answer entry that doesn't exist."""
    nonexistent_id = str(uuid4())
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{nonexistent_id}"
    payload = {"question": "Updated question", "groundtruth": "Updated answer"}

    response = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert response.status_code == 404


def test_delete_question_answer():
    """Test deleting a question-answer entry."""
    # First create a test entry
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}"
    payload = {"question": "Question to delete", "groundtruth": "Answer to delete"}

    create_response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    assert create_response.status_code == 200
    created_qa = create_response.json()
    question_answer_id = created_qa["id"]

    # Test deleting
    delete_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{question_answer_id}"
    response = client.delete(delete_endpoint, headers=HEADERS_JWT)
    result = response.json()

    assert response.status_code == 200
    assert isinstance(result, dict)
    assert "message" in result
    assert question_answer_id in result["message"]

    # Verify that the question-answer entry has been deleted
    get_endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{question_answer_id}"
    response = client.get(get_endpoint, headers=HEADERS_JWT)
    assert response.status_code == 404


def test_delete_nonexistent_question_answer():
    """Test deleting a question-answer entry that doesn't exist."""
    nonexistent_id = str(uuid4())
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}/{nonexistent_id}"
    response = client.delete(endpoint, headers=HEADERS_JWT)

    assert response.status_code == 404


def test_unauthorized_access():
    """Test accessing endpoints without proper authentication."""
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{TEST_PROJECT_ID}"

    # Test without headers
    response = client.get(endpoint)
    assert response.status_code == 403  # Forbidden - server refuses to authorize without credentials

    # Test with invalid token
    invalid_headers = {
        "accept": "application/json",
        "Authorization": "Bearer invalid_token",
    }
    response = client.get(endpoint, headers=invalid_headers)
    assert response.status_code == 401  # Unauthorized - invalid credentials


def test_invalid_organization_id():
    """Test accessing endpoints with invalid organization ID."""
    invalid_org_id = str(uuid4())
    endpoint = f"/question-answers/{invalid_org_id}/projects/{TEST_PROJECT_ID}"

    response = client.get(endpoint, headers=HEADERS_JWT)
    assert response.status_code == 403  # Should be forbidden if user doesn't have access


def test_invalid_project_id():
    """Test accessing endpoints with invalid project ID."""
    invalid_project_id = str(uuid4())
    endpoint = f"/question-answers/{ORGANIZATION_ID}/projects/{invalid_project_id}"

    response = client.get(endpoint, headers=HEADERS_JWT)
    assert response.status_code == 200  # Should return empty list for non-existent project
    question_answers = response.json()
    assert isinstance(question_answers, list)
    assert len(question_answers) == 0
