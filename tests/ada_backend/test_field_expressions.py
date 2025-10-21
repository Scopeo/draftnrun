"""
E2E test for field expressions functionality.
Tests the complete flow from field expression parsing to GraphRunner execution.
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from ada_backend.main import app
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings

# Test constants
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"  # umbrella organization
COMPONENT_ID = str(COMPONENT_UUIDS["llm_call"])
COMPONENT_VERSION_ID = str(COMPONENT_UUIDS["llm_call"])

client = TestClient(app)
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}


def test_field_expressions_e2e():
    """Test field expressions parsing and GraphRunner integration end-to-end."""
    # Create a unique project for this test
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"field_expressions_test_{project_id}",
        "description": "Test project for field expressions",
    }

    # Create project
    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200
    project_data = project_response.json()
    assert project_data["project_id"] == project_id
    assert project_data["project_name"] == f"field_expressions_test_{project_id}"

    # Get the auto-created draft graph runner ID
    project_details = client.get(f"/projects/{project_id}", headers=HEADERS_JWT).json()
    assert "graph_runners" in project_details
    assert len(project_details["graph_runners"]) > 0

    graph_runner_id = None
    for gr in project_details["graph_runners"]:
        if gr["env"] == "draft":
            graph_runner_id = gr["graph_runner_id"]
            break

    assert graph_runner_id is not None, "Draft graph runner should be auto-created"

    endpoint = f"/projects/{project_id}/graph/{graph_runner_id}"

    # Create component instances with field expressions
    src_instance_id = str(uuid4())
    dst_instance_id = str(uuid4())
    edge_id = str(uuid4())

    expression_text = f"Task: @{{{{{src_instance_id}.output}}}} - Style: @{{{{{src_instance_id}.output}}}}"

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
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [
                    {
                        "value": "Hello world",
                        "name": "prompt_template",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "Answer this question: {input}",
                        "ui_component": "Textarea",
                        "ui_component_properties": {},
                        "is_advanced": False,
                    },
                    {
                        "value": "openai:gpt-4o-mini",
                        "name": "completion_model",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "openai:gpt-4o-mini",
                        "ui_component": "Select",
                        "ui_component_properties": {},
                        "is_advanced": False,
                    },
                ],
                "tool_description": {
                    "name": "Test Tool",
                    "description": "Test Description",
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
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [
                    {
                        "value": "Process this: {input}",
                        "name": "prompt_template",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "Answer this question: {input}",
                        "ui_component": "Textarea",
                        "ui_component_properties": {},
                        "is_advanced": False,
                    },
                    {
                        "value": "openai:gpt-4o-mini",
                        "name": "completion_model",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "openai:gpt-4o-mini",
                        "ui_component": "Select",
                        "ui_component_properties": {},
                        "is_advanced": False,
                    },
                ],
                "tool_description": {
                    "name": "Test Tool",
                    "description": "Test Description",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "component_name": "LLM Call",
                "component_description": "Templated LLM Call",
                "field_expressions": [
                    {
                        "field_name": "prompt_template",
                        "expression_text": expression_text,
                    }
                ],
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
    }

    # Send request with field expressions
    put_resp = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["graph_id"] == graph_runner_id

    # Verify the graph was created successfully
    get_resp = client.get(endpoint, headers=HEADERS_JWT)
    assert get_resp.status_code == 200
    graph_data = get_resp.json()

    # Verify component instances were created
    assert "component_instances" in graph_data
    assert len(graph_data["component_instances"]) == 2

    # Verify edges were created
    assert "edges" in graph_data
    assert len(graph_data["edges"]) == 1
    assert graph_data["edges"][0]["origin"] == src_instance_id
    assert graph_data["edges"][0]["destination"] == dst_instance_id

    # Verify field expressions were processed and nested
    dst = next(ci for ci in graph_data["component_instances"] if ci["id"] == dst_instance_id)
    assert "field_expressions" in dst
    assert len(dst["field_expressions"]) == 1
    stored_expression = dst["field_expressions"][0]
    assert stored_expression["field_name"] == "prompt_template"
    assert "expression_json" in stored_expression

    # Verify the expression JSON structure
    expression_json = stored_expression["expression_json"]
    assert expression_json["type"] == "concat"
    assert "parts" in expression_json
    assert len(expression_json["parts"]) == 4  # "Task: ", ref, " - Style: ", ref

    # Verify the parts contain the expected structure
    parts = expression_json["parts"]
    assert parts[0]["type"] == "literal"
    assert parts[0]["value"] == "Task: "
    assert parts[1]["type"] == "ref"
    assert parts[1]["instance"] == src_instance_id
    assert parts[1]["port"] == "output"
    assert parts[2]["type"] == "literal"
    assert parts[2]["value"] == " - Style: "
    assert parts[3]["type"] == "ref"
    assert parts[3]["instance"] == src_instance_id
    assert parts[3]["port"] == "output"

    # Clean up test data
    delete_response = client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)
    assert delete_response.status_code == 200
    delete_data = delete_response.json()
    assert delete_data["project_id"] == project_id
    assert "graph_runner_ids" in delete_data
    assert len(delete_data["graph_runner_ids"]) > 0

    # Verify project was deleted
    get_project_resp = client.get(f"/projects/{project_id}", headers=HEADERS_JWT)
    assert get_project_resp.status_code == 404


def test_invalid_reference_uuid_returns_400():
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"field_expr_invalid_uuid_{project_id}",
        "description": "Test invalid ref uuid",
    }
    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    project_details = client.get(f"/projects/{project_id}", headers=HEADERS_JWT).json()
    graph_runner_id = next(gr["graph_runner_id"] for gr in project_details["graph_runners"] if gr["env"] == "draft")
    endpoint = f"/projects/{project_id}/graph/{graph_runner_id}"

    src_instance_id = str(uuid4())
    dst_instance_id = str(uuid4())
    edge_id = str(uuid4())

    bad_instance_id = "not-a-uuid"
    expression_text = f"@{{{{{bad_instance_id}.output}}}}"

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
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [],
                "tool_description": {
                    "name": "Test Tool",
                    "description": "d",
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
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [],
                "tool_description": {
                    "name": "Test Tool",
                    "description": "d",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "component_name": "LLM Call",
                "component_description": "Templated LLM Call",
                "field_expressions": [
                    {
                        "field_name": "prompt_template",
                        "expression_text": expression_text,
                    }
                ],
            },
        ],
        "relationships": [],
        "edges": [{"id": edge_id, "origin": src_instance_id, "destination": dst_instance_id, "order": 0}],
    }

    put_resp = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert put_resp.status_code == 400

    # Cleanup
    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)


def test_invalid_reference_unknown_port_returns_400():
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"field_expr_invalid_port_{project_id}",
        "description": "Test invalid ref port",
    }
    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    project_details = client.get(f"/projects/{project_id}", headers=HEADERS_JWT).json()
    graph_runner_id = next(gr["graph_runner_id"] for gr in project_details["graph_runners"] if gr["env"] == "draft")
    endpoint = f"/projects/{project_id}/graph/{graph_runner_id}"

    src_instance_id = str(uuid4())
    dst_instance_id = str(uuid4())
    edge_id = str(uuid4())

    expression_text = f"@{{{{{src_instance_id}.unknown_port}}}}"

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
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [],
                "tool_description": {
                    "name": "Test Tool",
                    "description": "d",
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
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [],
                "tool_description": {
                    "name": "Test Tool",
                    "description": "d",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "component_name": "LLM Call",
                "component_description": "Templated LLM Call",
                "field_expressions": [
                    {
                        "field_name": "prompt_template",
                        "expression_text": expression_text,
                    }
                ],
            },
        ],
        "relationships": [],
        "edges": [{"id": edge_id, "origin": src_instance_id, "destination": dst_instance_id, "order": 0}],
    }

    put_resp = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert put_resp.status_code == 400

    # Cleanup
    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)
