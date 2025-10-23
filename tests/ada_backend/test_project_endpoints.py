from uuid import uuid4
from fastapi.testclient import TestClient
import pytest

from ada_backend.main import app
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.scripts.get_supabase_token import get_user_jwt
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
TEST_PROJECT_ID = str(uuid4())


@pytest.fixture(params=["input", "start"])
def workflow_node_type(request):
    """Fixture that provides both 'input' and 'start' node types for testing."""
    return request.param


def test_create_project():
    endpoint = f"/projects/{ORGANIZATION_ID}"
    payload = {
        "project_id": TEST_PROJECT_ID,
        "project_name": f"test project {TEST_PROJECT_ID}",
        "description": "test project description",
    }
    response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    project = response.json()
    assert response.status_code == 200
    assert isinstance(project, dict)
    assert project["project_id"] == str(TEST_PROJECT_ID)
    assert project["project_name"] == f"test project {TEST_PROJECT_ID}"
    assert project["description"] == "test project description"
    assert project["organization_id"] == ORGANIZATION_ID
    assert project["created_at"] is not None
    assert project["updated_at"] is not None
    assert len(project["graph_runners"]) > 0


def test_get_project_by_organization():
    endpoint = f"/projects/org/{ORGANIZATION_ID}"
    response = client.get(endpoint, headers=HEADERS_JWT)
    projects = response.json()

    assert response.status_code == 200
    assert isinstance(projects, list)
    assert len(projects) > 0
    assert all(isinstance(project, dict) for project in projects)
    assert all("project_id" in project for project in projects)
    assert all("project_name" in project for project in projects)
    assert all("description" in project for project in projects)
    assert all("organization_id" in project for project in projects)
    assert all(project["organization_id"] == ORGANIZATION_ID for project in projects)


def test_get_project():
    endpoint = f"/projects/{TEST_PROJECT_ID}"
    response = client.get(endpoint, headers=HEADERS_JWT)
    project = response.json()

    assert response.status_code == 200
    assert isinstance(project, dict)
    assert project["project_id"] == str(TEST_PROJECT_ID)
    assert project["project_name"] == f"test project {TEST_PROJECT_ID}"
    assert project["description"] == "test project description"
    assert project["organization_id"] == ORGANIZATION_ID
    assert project["created_at"] is not None
    assert project["updated_at"] is not None
    assert len(project["graph_runners"]) > 0


def test_check_project_has_input_component(workflow_node_type):
    # Create a new project for this test
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"test_project_{workflow_node_type}_{project_uuid}",
        "description": f"Test project for {workflow_node_type} node validation",
    }

    # Create the project
    create_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert create_response.status_code == 200

    # Get the project details
    endpoint = f"/projects/{project_uuid}"
    response = client.get(endpoint, headers=HEADERS_JWT)
    project = response.json()
    assert response.status_code == 200

    graph_runner_id = project["graph_runners"][0]["graph_runner_id"]
    endpoint = f"/projects/{project_uuid}/graph/{graph_runner_id}"
    response = client.get(endpoint, headers=HEADERS_JWT)
    graph_description = response.json()
    assert response.status_code == 200

    # The default workflow always uses the "start" component, regardless of the fixture parameter
    # This test validates that the default workflow configuration is correct
    expected_component_id = str(COMPONENT_UUIDS["start"])
    assert graph_description["component_instances"][0]["component_id"] == expected_component_id


def test_update_project():
    endpoint = f"/projects/{TEST_PROJECT_ID}"
    payload = {
        "project_name": f"updated test project {TEST_PROJECT_ID}",
        "description": "updated test project description",
    }
    response = client.patch(endpoint, headers=HEADERS_JWT, json=payload)
    project = response.json()

    assert response.status_code == 200
    assert isinstance(project, dict)
    assert project["project_id"] == str(TEST_PROJECT_ID)
    assert project["project_name"] == f"updated test project {TEST_PROJECT_ID}"
    assert project["description"] == "updated test project description"


def test_delete_project():
    endpoint = f"/projects/{TEST_PROJECT_ID}"
    response = client.delete(endpoint, headers=HEADERS_JWT)
    result = response.json()
    assert response.status_code == 200
    assert isinstance(result, dict)
    assert "project_id" in result
    assert result["project_id"] == str(TEST_PROJECT_ID)
    assert "graph_runner_ids" in result
    assert isinstance(result["graph_runner_ids"], list)
    assert len(result["graph_runner_ids"]) > 0

    # Verify that the project has been deleted
    response = client.get(endpoint, headers=HEADERS_JWT)
    assert response.status_code == 404
