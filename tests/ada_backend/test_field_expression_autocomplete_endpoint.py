"""
E2E tests for the field expression autocomplete endpoint.
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from ada_backend.main import app
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings

client = TestClient(app)
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}
COMPONENT_ID = str(COMPONENT_UUIDS["llm_call"])
COMPONENT_VERSION_ID = str(COMPONENT_VERSION_UUIDS["llm_call"])
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"


def _create_component_instance(instance_id: str, name: str, is_start_node: bool) -> dict:
    params = [
        {"value": "Hello", "name": "prompt_template", "order": None},
        {"value": "openai:gpt-4o-mini", "name": "completion_model", "order": None},
        {"value": 0.2, "name": "default_temperature", "order": None},
    ]

    instance = {
        "is_agent": True,
        "is_protected": False,
        "function_callable": True,
        "can_use_function_calling": False,
        "tool_parameter_name": None,
        "subcomponents_info": [],
        "id": instance_id,
        "name": name,
        "ref": "",
        "is_start_node": is_start_node,
        "component_id": COMPONENT_ID,
        "component_version_id": COMPONENT_VERSION_ID,
        "parameters": params,
        "tool_description": {
            "name": "Test Tool",
            "description": "d",
            "tool_properties": {},
            "required_tool_properties": [],
        },
        "component_name": "LLM Call",
        "component_description": "Templated LLM Call",
    }
    return instance


def _create_graph_payload(src_instance_id: str, dst_instance_id: str, edge_id: str) -> dict:
    return {
        "component_instances": [
            _create_component_instance(
                instance_id=src_instance_id,
                name="Source Agent",
                is_start_node=True,
            ),
            _create_component_instance(
                instance_id=dst_instance_id,
                name="Target Agent",
                is_start_node=False,
            ),
        ],
        "relationships": [],
        "edges": [{"id": edge_id, "origin": src_instance_id, "destination": dst_instance_id, "order": 0}],
    }


def _create_project_and_get_endpoint(prefix: str) -> tuple[str, str]:
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"{prefix}_{project_id}",
        "description": f"Test {prefix}",
    }
    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    project_details = client.get(f"/projects/{project_id}", headers=HEADERS_JWT).json()
    graph_runner_id = next(gr["graph_runner_id"] for gr in project_details["graph_runners"] if gr["env"] == "draft")
    endpoint = f"/projects/{project_id}/graph/{graph_runner_id}"
    return project_id, endpoint


def test_field_expression_autocomplete_instance_and_port_suggestions():
    project_id, endpoint = _create_project_and_get_endpoint("autocomplete")
    src_instance_id = str(uuid4())
    dst_instance_id = str(uuid4())
    edge_id = str(uuid4())

    payload = _create_graph_payload(src_instance_id, dst_instance_id, edge_id)
    response = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert response.status_code == 200

    try:
        # Instance suggestions
        partial = src_instance_id[:8]
        instance_request = {
            "target_instance_id": dst_instance_id,
            "expression_text": "@{{" + partial,
            "cursor_offset": len("@{{" + partial),
        }
        autocomplete_response = client.post(
            f"{endpoint}/field-expressions/autocomplete",
            headers=HEADERS_JWT,
            json=instance_request,
        )
        assert autocomplete_response.status_code == 200
        suggestions = autocomplete_response.json()["suggestions"]
        assert any(s["detail"]["instance_id"] == src_instance_id for s in suggestions)

        # Port suggestions
        port_request = {
            "target_instance_id": dst_instance_id,
            "expression_text": "@{{" + src_instance_id + ".out",
            "cursor_offset": len("@{{" + src_instance_id + ".out"),
        }
        port_response = client.post(
            f"{endpoint}/field-expressions/autocomplete",
            headers=HEADERS_JWT,
            json=port_request,
        )
        assert port_response.status_code == 200
        port_suggestions = port_response.json()["suggestions"]
        assert any(s["detail"]["port_name"] == "output" for s in port_suggestions)

        # Cursor outside context should return empty suggestions
        empty_request = {
            "target_instance_id": dst_instance_id,
            "expression_text": "Hello world",
            "cursor_offset": 5,
        }
        empty_response = client.post(
            f"{endpoint}/field-expressions/autocomplete",
            headers=HEADERS_JWT,
            json=empty_request,
        )
        assert empty_response.status_code == 200
        assert empty_response.json()["suggestions"] == []
    finally:
        client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)


def test_field_expression_autocomplete_filters_out_downstream_instances_and_ports():
    project_id, endpoint = _create_project_and_get_endpoint("autocomplete_upstream")
    upstream_instance_id = str(uuid4())
    target_instance_id = str(uuid4())
    downstream_instance_id = str(uuid4())

    edges = [
        {"id": str(uuid4()), "origin": upstream_instance_id, "destination": target_instance_id, "order": 0},
        {"id": str(uuid4()), "origin": target_instance_id, "destination": downstream_instance_id, "order": 1},
    ]
    payload = {
        "component_instances": [
            _create_component_instance(upstream_instance_id, "Upstream Agent", True),
            _create_component_instance(target_instance_id, "Target Agent", False),
            _create_component_instance(downstream_instance_id, "Downstream Agent", False),
        ],
        "relationships": [],
        "edges": edges,
    }
    response = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert response.status_code == 200

    try:
        # Only upstream instance should surface in suggestions.
        request_payload = {
            "target_instance_id": target_instance_id,
            "expression_text": "@{{",
            "cursor_offset": len("@{{"),
        }
        autocomplete_response = client.post(
            f"{endpoint}/field-expressions/autocomplete",
            headers=HEADERS_JWT,
            json=request_payload,
        )
        assert autocomplete_response.status_code == 200
        suggestions = autocomplete_response.json()["suggestions"]
        assert any(s["detail"]["instance_id"] == upstream_instance_id for s in suggestions)
        assert all(
            s["detail"]["instance_id"] != downstream_instance_id
            for s in suggestions
            if s["detail"]["instance_id"] is not None
        )

        # Attempting to autocomplete ports for a downstream node should yield no suggestions.
        downstream_port_expression = "@{{" + downstream_instance_id + ".ou"
        port_request = {
            "target_instance_id": target_instance_id,
            "expression_text": downstream_port_expression,
            "cursor_offset": len(downstream_port_expression),
        }
        port_response = client.post(
            f"{endpoint}/field-expressions/autocomplete",
            headers=HEADERS_JWT,
            json=port_request,
        )
        assert port_response.status_code == 200
        assert port_response.json()["suggestions"] == []
    finally:
        client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)
