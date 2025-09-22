from uuid import UUID, uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from ada_backend.database.setup_db import SessionLocal
from ada_backend.main import app
from ada_backend.repositories.graph_runner_repository import delete_graph_runner
from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings

client = TestClient(app)
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"  # umbrella organization
PROJECT_ID = "f7ddbfcb-6843-4ae9-a15b-40aa565b955b"  # graph test project
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}

GRAPH_RUNNER_ID = str(uuid4())


# Mock cipher for testing
class MockCipher:
    def encrypt(self, data: bytes) -> bytes:
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data


# Apply the mock cipher to all tests
@pytest.fixture(autouse=True)
def mock_cipher():
    with patch("ada_backend.database.models.CIPHER", MockCipher()):
        yield


def test_create_empty_graph_runner():
    """
    Create a empty graph runner.
    """
    endpoint = f"/projects/{PROJECT_ID}/graph/{GRAPH_RUNNER_ID}"
    payload = {
        "component_instances": [],
        "relationships": [],
        "edges": [],
        "tag_version": None,
    }

    response = client.put(endpoint, headers=HEADERS_JWT, json=payload)

    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert response.json()["graph_id"] == GRAPH_RUNNER_ID

    response = client.get(endpoint, headers=HEADERS_JWT)
    results = response.json()
    print("here")
    print(results)
    assert response.status_code == 200
    assert isinstance(results, dict)
    assert results == payload


def test_update_graph_runner():
    """
    Update the graph runner.
    """
    endpoint = f"/projects/{PROJECT_ID}/graph/{GRAPH_RUNNER_ID}"
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
                "component_id": "7a039611-49b3-4bfd-b09b-c0f93edf3b79",
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
                "component_id": "7a039611-49b3-4bfd-b09b-c0f93edf3b79",
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
    assert response.json()["graph_id"] == GRAPH_RUNNER_ID

    response = client.get(endpoint, headers=HEADERS_JWT)
    results = response.json()
    assert response.status_code == 200
    assert isinstance(results, dict)
    assert len(results["component_instances"]) == len(payload["component_instances"])
    assert results["component_instances"][0]["id"] == payload["component_instances"][0]["id"]
    assert results["component_instances"][1]["id"] == payload["component_instances"][1]["id"]
    assert results["component_instances"][0]["component_id"] == payload["component_instances"][0]["component_id"]
    assert results["component_instances"][1]["component_id"] == payload["component_instances"][1]["component_id"]
    assert results["relationships"] == payload["relationships"]
    assert results["edges"] == payload["edges"]


def test_delete_graph_runner():
    session = SessionLocal()
    graph_id = UUID(GRAPH_RUNNER_ID)
    delete_graph_runner(session, graph_id)

    endpoint = f"/projects/{PROJECT_ID}/graph/{GRAPH_RUNNER_ID}"
    response = client.get(endpoint, headers=HEADERS_JWT)
    assert response.status_code == 400
