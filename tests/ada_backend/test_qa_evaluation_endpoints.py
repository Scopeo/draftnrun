import pytest
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient

from ada_backend.main import app
from ada_backend.scripts.get_supabase_token import get_user_jwt
from ada_backend.database.models import EvaluationType
from ada_backend.schemas.qa_evaluation_schema import (
    BooleanEvaluationResult,
    ScoreEvaluationResult,
    FreeTextEvaluationResult,
)
from settings import settings

client = TestClient(app)
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}

MOCK_LLM_SERVICE_PATH = (
    "ada_backend.services.qa.qa_evaluation_service." "CompletionService.constrained_complete_with_pydantic_async"
)


@pytest.fixture
def test_project():
    """Create a test project and clean it up after the test."""
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"qa_evaluation_test_{project_id}",
        "description": "Test project for QA evaluation",
    }
    response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert response.status_code == 200
    yield project_id
    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)


@pytest.fixture
def evaluation_scenario(test_project):
    """Create a complete evaluation scenario with project, dataset, input, version_output, and judge."""
    project_response = client.get(f"/projects/{test_project}", headers=HEADERS_JWT)
    assert project_response.status_code == 200
    project_data = project_response.json()
    graph_runner_id = None
    for gr in project_data["graph_runners"]:
        if gr["env"] == "draft":
            graph_runner_id = gr["graph_runner_id"]
            break
    assert graph_runner_id is not None, "Draft graph runner not found"

    dataset_payload = {"datasets_name": [f"test_dataset_{uuid4()}"]}
    dataset_response = client.post(f"/projects/{test_project}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    input_payload = {
        "inputs_groundtruths": [
            {
                "input": {"messages": [{"role": "user", "content": "What is 2 + 2?"}]},
                "groundtruth": "4",
            }
        ]
    }
    input_response = client.post(
        f"/projects/{test_project}/qa/datasets/{dataset_id}/entries", headers=HEADERS_JWT, json=input_payload
    )
    assert input_response.status_code == 200
    input_id = input_response.json()["inputs_groundtruths"][0]["id"]

    run_payload = {"graph_runner_id": graph_runner_id, "input_ids": [input_id]}
    run_response = client.post(
        f"/projects/{test_project}/qa/datasets/{dataset_id}/run", headers=HEADERS_JWT, json=run_payload
    )
    assert run_response.status_code == 200

    version_output_response = client.get(
        f"/projects/{test_project}/qa/version-outputs?graph_runner_id={graph_runner_id}&input_ids={input_id}",
        headers=HEADERS_JWT,
    )
    assert version_output_response.status_code == 200
    version_output_ids = version_output_response.json()
    assert input_id in version_output_ids
    assert version_output_ids[input_id] is not None
    version_output_id = version_output_ids[input_id]

    judge_data = {
        "name": f"Test Judge {uuid4()}",
        "evaluation_type": EvaluationType.BOOLEAN,
        "prompt_template": "Test prompt template",
    }
    judge_response = client.post(f"/projects/{test_project}/qa/llm-judges", headers=HEADERS_JWT, json=judge_data)
    assert judge_response.status_code == 200
    judge_id = judge_response.json()["id"]

    return {
        "project_id": test_project,
        "graph_runner_id": graph_runner_id,
        "dataset_id": dataset_id,
        "input_id": input_id,
        "version_output_id": version_output_id,
        "judge_id": judge_id,
    }


@pytest.fixture
def mock_llm_service():
    with patch(MOCK_LLM_SERVICE_PATH) as mock:
        mock.return_value = BooleanEvaluationResult(result=True, justification="Mock justification")
        yield mock


def test_llm_judge_management(test_project):
    """Test complete LLM judge CRUD operations."""
    response = client.get(f"/projects/{test_project}/qa/llm-judges", headers=HEADERS_JWT)
    assert response.status_code == 200
    assert response.json() == []

    create_data = {
        "name": "Test Judge",
        "description": "Test description",
        "evaluation_type": EvaluationType.BOOLEAN,
        "prompt_template": "Test: {{input}}",
    }
    response = client.post(f"/projects/{test_project}/qa/llm-judges", headers=HEADERS_JWT, json=create_data)
    assert response.status_code == 200
    judge = response.json()
    assert judge["name"] == "Test Judge"
    assert judge["description"] == "Test description"
    assert judge["evaluation_type"] == "boolean"
    assert judge["llm_model_reference"] == "openai:gpt-5-mini"
    assert judge["temperature"] == 1.0
    assert judge["project_id"] == test_project
    assert "id" in judge
    assert "created_at" in judge
    judge_id = judge["id"]

    response = client.get(f"/projects/{test_project}/qa/llm-judges", headers=HEADERS_JWT)
    assert response.status_code == 200
    judges = response.json()
    assert len(judges) == 1
    assert judges[0]["id"] == judge_id

    update_data = {"name": "Updated Judge Name"}
    response = client.patch(
        f"/projects/{test_project}/qa/llm-judges/{judge_id}", headers=HEADERS_JWT, json=update_data
    )
    assert response.status_code == 200
    updated_judge = response.json()
    assert updated_judge["name"] == "Updated Judge Name"
    assert updated_judge["evaluation_type"] == "boolean"

    update_data = {"description": "Updated description", "temperature": 0.9}
    response = client.patch(
        f"/projects/{test_project}/qa/llm-judges/{judge_id}", headers=HEADERS_JWT, json=update_data
    )
    assert response.status_code == 200
    updated_judge = response.json()
    assert updated_judge["description"] == "Updated description"
    assert updated_judge["temperature"] == 0.9

    delete_payload = [judge_id]
    response = client.request(
        method="DELETE", url=f"/projects/{test_project}/qa/llm-judges", headers=HEADERS_JWT, json=delete_payload
    )
    assert response.status_code == 204

    response = client.get(f"/projects/{test_project}/qa/llm-judges", headers=HEADERS_JWT)
    assert response.status_code == 200
    assert response.json() == []

    non_existent_judge_id = str(uuid4())
    response = client.patch(
        f"/projects/{test_project}/qa/llm-judges/{non_existent_judge_id}",
        headers=HEADERS_JWT,
        json={"name": "Test"},
    )
    assert response.status_code == 400


def test_llm_judge_defaults():
    for evaluation_type in ["boolean", "score", "free_text"]:
        response = client.get(f"/qa/llm-judges/defaults?evaluation_type={evaluation_type}", headers=HEADERS_JWT)
        assert response.status_code == 200
        template = response.json()
        assert template["evaluation_type"] == evaluation_type
        assert "prompt_template" in template
        assert isinstance(template["prompt_template"], str)
        assert len(template["prompt_template"]) > 0


@patch(MOCK_LLM_SERVICE_PATH)
def test_get_evaluations(mock_llm, evaluation_scenario):
    project_id = evaluation_scenario["project_id"]
    version_output_id = evaluation_scenario["version_output_id"]

    response = client.get(
        f"/projects/{project_id}/qa/version-outputs/{version_output_id}/evaluations", headers=HEADERS_JWT
    )
    assert response.status_code == 200
    assert response.json() == []


@patch(MOCK_LLM_SERVICE_PATH)
def test_run_evaluation_boolean(mock_llm, evaluation_scenario):
    mock_llm.return_value = BooleanEvaluationResult(result=True, justification="Test justification")
    project_id = evaluation_scenario["project_id"]
    version_output_id = evaluation_scenario["version_output_id"]
    judge_id = evaluation_scenario["judge_id"]

    payload = {"version_output_id": version_output_id}
    response = client.post(
        f"/projects/{project_id}/qa/llm-judges/{judge_id}/evaluations/run", headers=HEADERS_JWT, json=payload
    )
    assert response.status_code == 200
    evaluation = response.json()
    assert evaluation["judge_id"] == judge_id
    assert evaluation["version_output_id"] == version_output_id
    assert evaluation["evaluation_result"]["type"] == "boolean"
    assert "result" in evaluation["evaluation_result"]
    assert "justification" in evaluation["evaluation_result"]


@patch(MOCK_LLM_SERVICE_PATH)
def test_run_evaluation_score(mock_llm, evaluation_scenario):
    mock_llm.return_value = ScoreEvaluationResult(score=4, max_score=4, justification="Test score justification")
    project_id = evaluation_scenario["project_id"]
    version_output_id = evaluation_scenario["version_output_id"]

    judge_data = {
        "name": f"Score Judge {uuid4()}",
        "evaluation_type": EvaluationType.SCORE,
        "prompt_template": "Test: {{input}}",
    }
    response = client.post(f"/projects/{project_id}/qa/llm-judges", headers=HEADERS_JWT, json=judge_data)
    assert response.status_code == 200
    judge_id = response.json()["id"]

    payload = {"version_output_id": version_output_id}
    response = client.post(
        f"/projects/{project_id}/qa/llm-judges/{judge_id}/evaluations/run", headers=HEADERS_JWT, json=payload
    )
    assert response.status_code == 200
    evaluation = response.json()
    assert evaluation["evaluation_result"]["type"] == "score"
    assert "score" in evaluation["evaluation_result"]
    assert "max_score" in evaluation["evaluation_result"]


@patch(MOCK_LLM_SERVICE_PATH)
def test_run_evaluation_free_text(mock_llm, evaluation_scenario):
    mock_llm.return_value = FreeTextEvaluationResult(result="Good", justification="Test free text justification")
    project_id = evaluation_scenario["project_id"]
    version_output_id = evaluation_scenario["version_output_id"]

    judge_data = {
        "name": f"Free Text Judge {uuid4()}",
        "evaluation_type": EvaluationType.FREE_TEXT,
        "prompt_template": "Test: {{input}}",
    }
    response = client.post(f"/projects/{project_id}/qa/llm-judges", headers=HEADERS_JWT, json=judge_data)
    assert response.status_code == 200
    judge_id = response.json()["id"]

    payload = {"version_output_id": version_output_id}
    response = client.post(
        f"/projects/{project_id}/qa/llm-judges/{judge_id}/evaluations/run", headers=HEADERS_JWT, json=payload
    )
    assert response.status_code == 200
    evaluation = response.json()
    assert evaluation["evaluation_result"]["type"] == "free_text"
    assert "result" in evaluation["evaluation_result"]


@patch(MOCK_LLM_SERVICE_PATH)
def test_delete_evaluations(mock_llm, evaluation_scenario):
    mock_llm.return_value = BooleanEvaluationResult(result=True, justification="Test justification")
    project_id = evaluation_scenario["project_id"]
    version_output_id = evaluation_scenario["version_output_id"]
    judge_id = evaluation_scenario["judge_id"]

    payload = {"version_output_id": version_output_id}
    response = client.post(
        f"/projects/{project_id}/qa/llm-judges/{judge_id}/evaluations/run", headers=HEADERS_JWT, json=payload
    )
    assert response.status_code == 200
    evaluation_id = response.json()["id"]

    delete_payload = [evaluation_id]
    response = client.request(
        method="DELETE", url=f"/projects/{project_id}/qa/evaluations", headers=HEADERS_JWT, json=delete_payload
    )
    assert response.status_code == 204

    response = client.request(
        method="DELETE", url=f"/projects/{project_id}/qa/evaluations", headers=HEADERS_JWT, json=delete_payload
    )  # idempotent
    assert response.status_code == 204

    response = client.get(
        f"/projects/{project_id}/qa/version-outputs/{version_output_id}/evaluations", headers=HEADERS_JWT
    )
    assert response.status_code == 200
    assert response.json() == []


@patch(MOCK_LLM_SERVICE_PATH)
def test_evaluation_errors(mock_llm, evaluation_scenario, test_project):
    project_id = evaluation_scenario["project_id"]
    version_output_id = evaluation_scenario["version_output_id"]

    non_existent_judge_id = str(uuid4())
    payload = {"version_output_id": version_output_id}
    response = client.post(
        f"/projects/{project_id}/qa/llm-judges/{non_existent_judge_id}/evaluations/run",
        headers=HEADERS_JWT,
        json=payload,
    )
    assert response.status_code == 400

    headers_no_auth = {"accept": "application/json"}
    response = client.get(f"/projects/{test_project}/qa/llm-judges", headers=headers_no_auth)
    assert response.status_code in [401, 403]

    response = client.get(
        f"/projects/{project_id}/qa/version-outputs/{version_output_id}/evaluations", headers=headers_no_auth
    )
    assert response.status_code in [401, 403]


def test_create_judge_validation_missing_evaluation_type(test_project):
    judge_data = {
        "name": "Test Judge",
        "prompt_template": "Test: {{input}}",
    }
    response = client.post(f"/projects/{test_project}/qa/llm-judges", headers=HEADERS_JWT, json=judge_data)
    assert response.status_code == 422


def test_create_judge_validation_invalid_uuid(test_project):
    judge_data = {
        "name": "Test Judge",
        "evaluation_type": EvaluationType.BOOLEAN,
        "prompt_template": "Test: {{input}}",
    }
    response = client.post("/projects/invalid-uuid/qa/llm-judges", headers=HEADERS_JWT, json=judge_data)
    assert response.status_code == 422


def test_run_evaluation_validation_missing_version_output_id(evaluation_scenario):
    project_id = evaluation_scenario["project_id"]
    judge_id = evaluation_scenario["judge_id"]

    response = client.post(
        f"/projects/{project_id}/qa/llm-judges/{judge_id}/evaluations/run", headers=HEADERS_JWT, json={}
    )
    assert response.status_code == 422
