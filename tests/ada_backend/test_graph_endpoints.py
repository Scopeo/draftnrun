from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.database.setup_db import SessionLocal
from ada_backend.main import app
from ada_backend.repositories.graph_runner_repository import delete_graph_runner
from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings

client = TestClient(app)
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"  # umbrella organization
PROJECT_ID = "9ae2def9-a04b-40a8-abe8-89264a418bfd"  # test project ID for mocked tests
GRAPH_RUNNER_ID = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"  # test graph runner ID for mocked tests
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}
COMPONENT_ID = str(COMPONENT_UUIDS["llm_call"])
COMPONENT_VERSION_ID = str(COMPONENT_VERSION_UUIDS["llm_call"])


def test_create_empty_graph_runner():
    """
    Create a empty graph runner.
    """
    # Create a unique project for this test to avoid constraint violations
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"empty_graph_test_{project_id}",
        "description": "Test project for empty graph runner",
    }
    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    # Get the auto-created draft graph runner ID
    project_details = client.get(f"/projects/{project_id}", headers=HEADERS_JWT).json()
    graph_runner_id = None
    for gr in project_details["graph_runners"]:
        if gr["env"] == "draft":
            graph_runner_id = gr["graph_runner_id"]
            break
    assert graph_runner_id is not None, "Draft graph runner should be auto-created"

    endpoint = f"/projects/{project_id}/graph/{graph_runner_id}"
    payload = {
        "component_instances": [],
        "relationships": [],
        "edges": [],
        "tag_name": None,
        "change_log": None,
    }

    response = client.put(endpoint, headers=HEADERS_JWT, json=payload)

    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert response.json()["graph_id"] == graph_runner_id

    response = client.get(endpoint, headers=HEADERS_JWT)
    results = response.json()
    assert response.status_code == 200
    assert isinstance(results, dict)
    # GET should include port_mappings; field expressions now nested per component instance
    expected = {**payload, "port_mappings": []}
    assert results["port_mappings"] == []
    assert results["component_instances"] == expected["component_instances"]
    assert results["relationships"] == expected["relationships"]
    assert results["edges"] == expected["edges"]

    # Cleanup
    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)


def test_update_graph_runner():
    """
    Update the graph runner.
    """
    # Create a unique project for this test to avoid constraint violations
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"update_graph_test_{project_id}",
        "description": "Test project for updating graph runner",
    }
    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    # Get the auto-created draft graph runner ID
    project_details = client.get(f"/projects/{project_id}", headers=HEADERS_JWT).json()
    graph_runner_id = None
    for gr in project_details["graph_runners"]:
        if gr["env"] == "draft":
            graph_runner_id = gr["graph_runner_id"]
            break
    assert graph_runner_id is not None, "Draft graph runner should be auto-created"

    endpoint = f"/projects/{project_id}/graph/{graph_runner_id}"
    component_instance_1_id = str(uuid4())
    component_instance_2_id = str(uuid4())
    edge_id = str(uuid4())
    payload = {
        "component_instances": [
            {
                "is_agent": True,
                "is_protected": False,
                "function_callable": True,
                "can_use_function_calling": False,
                "tool_parameter_name": None,
                "subcomponents_info": [],
                "id": component_instance_1_id,
                "name": "LLM Call",
                "ref": "",
                "is_start_node": True,
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [
                    {
                        "value": "Reformulate the question as a customer service query :\n{question}",
                        "name": "prompt_template",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "Answer this question: {input}",
                        "ui_component": "Textarea",
                        "ui_component_properties": {
                            "label": "Prompt Template",
                            "placeholder": "Enter the prompt here. Use {input} (or similar) "
                            "to insert dynamic content -  the {} braces with a keyword are mandatory.",
                        },
                        "is_advanced": False,
                    },
                    {
                        "value": "openai:gpt-4o-mini",
                        "name": "completion_model",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "openai:gpt-4.1-mini",
                        "ui_component": "Select",
                        "ui_component_properties": {
                            "label": "Model Name",
                            "options": [
                                {"value": "openai:gpt-4.1", "label": "GPT-4.1"},
                                {"value": "openai:gpt-4.1-mini", "label": "GPT-4.1 Mini"},
                                {"value": "openai:gpt-4.1-nano", "label": "GPT-4.1 Nano"},
                                {"value": "openai:gpt-4o", "label": "GPT-4o"},
                                {"value": "openai:gpt-4o-mini", "label": "GPT-4o Mini"},
                                {"value": "openai:o4-mini-2025-04-16", "label": "GPT-4o4-mini"},
                                {"value": "openai:o3-2025-04-16", "label": "GPT-4o3"},
                                {"value": "google:gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
                                {"value": "google:gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
                                {"value": "mistral:mistral-large", "label": "Mistral Large"},
                                {"value": "mistral:mistral-small-3", "label": "Mistral Small 3"},
                            ],
                        },
                        "is_advanced": False,
                    },
                ],
                "tool_description": {
                    "name": "Graph Test Chatbot",
                    "description": "Graph Test for Revaline",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "component_name": "LLM Call",
                "component_description": "Templated LLM Call",
            },
            {
                "is_agent": True,
                "is_protected": False,
                "function_callable": True,
                "can_use_function_calling": False,
                "tool_parameter_name": None,
                "subcomponents_info": [],
                "id": component_instance_2_id,
                "name": "Polite LLM",
                "ref": "",
                "is_start_node": False,
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [
                    {
                        "value": "Add polite expressions to the question: {question} \n",
                        "name": "prompt_template",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "Answer this question: {input}",
                        "ui_component": "Textarea",
                        "ui_component_properties": {
                            "label": "Prompt Template",
                            "placeholder": "Enter the prompt here. Use {input} (or similar) "
                            "to insert dynamic content -  the {} braces with a keyword are mandatory.",
                        },
                        "is_advanced": False,
                    },
                    {
                        "value": "openai:gpt-4o-mini",
                        "name": "completion_model",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "openai:gpt-4.1-mini",
                        "ui_component": "Select",
                        "ui_component_properties": {
                            "label": "Model Name",
                            "options": [
                                {"value": "openai:gpt-4.1", "label": "GPT-4.1"},
                                {"value": "openai:gpt-4.1-mini", "label": "GPT-4.1 Mini"},
                                {"value": "openai:gpt-4.1-nano", "label": "GPT-4.1 Nano"},
                                {"value": "openai:gpt-4o", "label": "GPT-4o"},
                                {"value": "openai:gpt-4o-mini", "label": "GPT-4o Mini"},
                                {"value": "openai:o4-mini-2025-04-16", "label": "GPT-4o4-mini"},
                                {"value": "openai:o3-2025-04-16", "label": "GPT-4o3"},
                                {"value": "google:gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
                                {"value": "google:gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
                                {"value": "mistral:mistral-large", "label": "Mistral Large"},
                                {"value": "mistral:mistral-small-3", "label": "Mistral Small 3"},
                            ],
                        },
                        "is_advanced": False,
                    },
                ],
                "tool_description": {
                    "name": "Graph Test Chatbot",
                    "description": "Graph Test for Revaline",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "component_name": "LLM Call",
                "component_description": "Templated LLM Call",
            },
        ],
        "relationships": [],
        "edges": [
            {
                "id": edge_id,
                "origin": component_instance_1_id,
                "destination": component_instance_2_id,
                "order": 1,
            },
        ],
    }

    response = client.put(endpoint, headers=HEADERS_JWT, json=payload)

    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert response.json()["graph_id"] == graph_runner_id

    response = client.get(endpoint, headers=HEADERS_JWT)
    results = response.json()
    assert response.status_code == 200
    assert isinstance(results, dict)
    assert len(results["component_instances"]) == len(payload["component_instances"])

    # Verify all expected IDs are present
    expected_ids = {ci["id"] for ci in payload["component_instances"]}
    actual_ids = {ci["id"] for ci in results["component_instances"]}
    assert actual_ids == expected_ids

    # Verify component IDs are correct
    expected_component_ids = {ci["component_id"] for ci in payload["component_instances"]}
    actual_component_ids = {ci["component_id"] for ci in results["component_instances"]}
    assert actual_component_ids == expected_component_ids
    assert results["relationships"] == payload["relationships"]
    assert results["edges"] == payload["edges"]

    # Cleanup
    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)


def test_delete_graph_runner():
    # Create a unique project for this test to avoid constraint violations
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"delete_graph_test_{project_id}",
        "description": "Test project for deleting graph runner",
    }
    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    # Get the auto-created draft graph runner ID
    project_details = client.get(f"/projects/{project_id}", headers=HEADERS_JWT).json()
    graph_runner_id = None
    for gr in project_details["graph_runners"]:
        if gr["env"] == "draft":
            graph_runner_id = gr["graph_runner_id"]
            break
    assert graph_runner_id is not None, "Draft graph runner should be auto-created"

    # Verify the graph runner exists
    endpoint = f"/projects/{project_id}/graph/{graph_runner_id}"
    response = client.get(endpoint, headers=HEADERS_JWT)
    assert response.status_code == 200

    # Now delete it
    session = SessionLocal()
    try:
        graph_id = UUID(graph_runner_id)
        delete_graph_runner(session, graph_id)
    finally:
        session.close()

    # Verify it's gone
    response = client.get(endpoint, headers=HEADERS_JWT)
    assert response.status_code == 400


def test_load_copy_graph_endpoint_success(monkeypatch):
    """When load_copy_graph_service returns a GraphLoadResponse, endpoint should return 200."""
    endpoint = f"/projects/{PROJECT_ID}/graph/{GRAPH_RUNNER_ID}/load-copy"

    # Build a minimal GraphLoadResponse-like dict
    payload = {"component_instances": [], "relationships": [], "edges": []}

    monkeypatch.setattr(
        "ada_backend.routers.graph_router.load_copy_graph_service",
        lambda session, project_id_to_copy, graph_runner_id_to_copy: payload,
    )

    response = client.get(endpoint, headers=HEADERS_JWT)
    assert response.status_code == 200
    assert response.json() == payload


def test_load_copy_graph_endpoint_value_error(monkeypatch):
    """When service raises ValueError, endpoint should return 400."""
    endpoint = f"/projects/{PROJECT_ID}/graph/{GRAPH_RUNNER_ID}/load-copy"

    def fake(session, project_id_to_copy, graph_runner_id_to_copy):
        raise ValueError("invalid relationship")

    monkeypatch.setattr("ada_backend.routers.graph_router.load_copy_graph_service", fake)

    response = client.get(endpoint, headers=HEADERS_JWT)
    assert response.status_code == 400


def test_load_copy_graph_endpoint_unexpected_error(monkeypatch):
    """When service raises unexpected exception, endpoint should return 500."""
    endpoint = f"/projects/{PROJECT_ID}/graph/{GRAPH_RUNNER_ID}/load-copy"

    def fake(session, project_id_to_copy, graph_runner_id_to_copy):
        raise RuntimeError("boom")

    monkeypatch.setattr("ada_backend.routers.graph_router.load_copy_graph_service", fake)

    response = client.get(endpoint, headers=HEADERS_JWT)
    assert response.status_code == 500
