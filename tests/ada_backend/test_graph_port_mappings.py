from uuid import UUID, uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from ada_backend.main import app
from ada_backend.database.setup_db import SessionLocal
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


# Mock cipher for testing
class MockCipher:
    def encrypt(self, data: bytes) -> bytes:
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data


# Apply the mock cipher to all tests in this module
@pytest.fixture(autouse=True)
def mock_cipher():
    with patch("ada_backend.database.models.CIPHER", MockCipher()):
        yield


def test_get_put_roundtrip_port_mappings_migration():
    """
    For an unmigrated graph (no port_mappings provided on PUT), verify that:
    - PUT succeeds
    - GET returns explicit auto-generated port_mappings
    - Using that GET payload (minus non-updatable fields) on PUT works (idempotent)
    - Subsequent GET returns the same explicit port_mappings
    """

    graph_runner_id = str(uuid4())
    endpoint = f"/projects/{PROJECT_ID}/graph/{graph_runner_id}"

    # Two component instances connected by a single edge; no port_mappings in the payload
    src_instance_id = str(uuid4())
    dst_instance_id = str(uuid4())
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
                "id": src_instance_id,
                "name": "Source Agent",
                "ref": "",
                "is_start_node": True,
                # Reuse seeded component id from existing tests
                "component_id": "7a039611-49b3-4bfd-b09b-c0f93edf3b79",
                "parameters": [],
                "tool_description": {
                    "name": "Graph Test Chatbot",
                    "description": "Graph Test",
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
                "id": dst_instance_id,
                "name": "Target Agent",
                "ref": "",
                "is_start_node": False,
                # Same seeded component as above to keep it simple
                "component_id": "7a039611-49b3-4bfd-b09b-c0f93edf3b79",
                "parameters": [],
                "tool_description": {
                    "name": "Graph Test Chatbot",
                    "description": "Graph Test",
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
                "origin": src_instance_id,
                "destination": dst_instance_id,
                "order": 0,
            }
        ],
        # Intentionally omit port_mappings -> backend should synthesize defaults on save
    }

    put_resp = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["graph_id"] == graph_runner_id

    # GET should now include explicit port_mappings created by the backend
    get_resp = client.get(endpoint, headers=HEADERS_JWT)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "port_mappings" in data
    assert isinstance(data["port_mappings"], list)
    assert len(data["port_mappings"]) == 1
    pm = data["port_mappings"][0]
    assert pm["source_instance_id"] == src_instance_id
    assert pm["target_instance_id"] == dst_instance_id
    assert pm["source_port_name"] == "output"
    assert pm["target_port_name"] == "input"
    assert pm["dispatch_strategy"] == "direct"

    # Roundtrip: PUT the GET response back (dropping non-updatable fields)
    roundtrip_payload = {
        k: data[k] for k in ("component_instances", "relationships", "edges", "port_mappings") if k in data
    }
    rt_put_resp = client.put(endpoint, headers=HEADERS_JWT, json=roundtrip_payload)
    assert rt_put_resp.status_code == 200

    # GET again; port_mappings should remain the same (idempotent)
    get_resp2 = client.get(endpoint, headers=HEADERS_JWT)
    assert get_resp2.status_code == 200
    data2 = get_resp2.json()
    assert data2.get("port_mappings") == data.get("port_mappings")

    # Cleanup this graph runner
    session = SessionLocal()
    delete_graph_runner(session, UUID(graph_runner_id))
