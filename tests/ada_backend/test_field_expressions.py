"""
E2E test for field expressions functionality.
Tests the complete flow from field expression parsing to GraphRunner execution.
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.main import app
from ada_backend.schemas.parameter_schema import ParameterKind
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


def _get_field_expressions_from_instance(instance: dict) -> list[dict]:
    """
    Helper to get field_expressions from a component instance.
    Reads ONLY from parameters[kind="input"] (new unified format).
    Returns list with field_name and expression_text.
    """
    input_params = [p for p in instance.get("parameters", []) if p.get("kind") == ParameterKind.INPUT]

    field_expressions = []
    for param in input_params:
        if param.get("value"):
            field_expressions.append({
                "field_name": param["name"],
                "expression_text": str(param["value"]),
            })

    return field_expressions


def _create_component_instance(
    instance_id: str,
    name: str,
    is_start_node: bool,
    prompt_template_value: str,
    input_expression: dict | None = None,
) -> dict:
    params = [
        {"value": prompt_template_value, "name": "prompt_template", "order": None},
        {"value": "openai:gpt-4o-mini", "name": "completion_model", "order": None},
        {"value": 0.2, "name": "default_temperature", "order": None},
    ]

    if input_expression:
        params.append({
            "name": input_expression["field_name"],
            "value": input_expression["expression_text"],
            "kind": ParameterKind.INPUT,
            "order": None,
        })

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


def _create_graph_payload_with_field_expressions(
    src_instance_id: str,
    dst_instance_id: str,
    edge_id: str,
    expression_text: str,
) -> dict:
    return {
        "component_instances": [
            _create_component_instance(
                instance_id=src_instance_id,
                name="Source Agent",
                is_start_node=True,
                prompt_template_value="Hello",
            ),
            _create_component_instance(
                instance_id=dst_instance_id,
                name="Target Agent",
                is_start_node=False,
                prompt_template_value="Process: {input}",
                input_expression={"field_name": "messages", "expression_text": expression_text},
            ),
        ],
        "relationships": [],
        "edges": [{"id": edge_id, "origin": src_instance_id, "destination": dst_instance_id, "order": 0}],
    }


def _create_project_and_get_endpoint(project_name_prefix: str) -> tuple[str, str]:
    project_id = str(uuid4())
    project_response = client.post(
        f"/projects/{ORGANIZATION_ID}",
        headers=HEADERS_JWT,
        json={
            "project_id": project_id,
            "project_name": f"{project_name_prefix}_{project_id}",
            "description": f"Test {project_name_prefix}",
        },
    )
    assert project_response.status_code == 200

    project_details = client.get(f"/projects/{project_id}", headers=HEADERS_JWT).json()
    graph_runner_id = next(gr["graph_runner_id"] for gr in project_details["graph_runners"] if gr["env"] == "draft")
    endpoint = f"/projects/{project_id}/graph/{graph_runner_id}"
    return project_id, endpoint


def _assert_expression_remapped(
    expr_json: dict,
    expr_text: str,
    original_instance_id: str,
    new_instance_id: str,
    context: str = "",
) -> None:
    """Assert that expression has been remapped from original_instance_id to new_instance_id."""
    assert str(original_instance_id) not in expr_text, (
        f"{context}Old instance ID {original_instance_id} should not be in expression"
    )
    assert str(new_instance_id) in expr_text, f"{context}New instance ID {new_instance_id} should be in expression"

    if expr_json["type"] == "ref":
        assert expr_json["instance"] == str(new_instance_id), (
            f"{context}Ref should use new instance ID {new_instance_id}, got {expr_json['instance']}"
        )
        assert expr_json["instance"] != str(original_instance_id), (
            f"{context}Ref should not use old instance ID {original_instance_id}"
        )
    elif expr_json["type"] == "concat":
        for part in expr_json["parts"]:
            if part["type"] == "ref":
                assert part["instance"] == str(new_instance_id), (
                    f"{context}Ref part should use new instance ID {new_instance_id}, got {part['instance']}"
                )
                assert part["instance"] != str(original_instance_id), (
                    f"{context}Ref part should not use old instance ID {original_instance_id}"
                )


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
                "tool_description": {
                    "name": "Test Tool",
                    "description": "Test Description",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "component_name": "LLM Call",
                "component_description": "Templated LLM Call",
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
                    {
                        "name": "messages",
                        "value": expression_text,
                        "kind": ParameterKind.INPUT,
                        "order": None,
                    },
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
    field_expressions = _get_field_expressions_from_instance(dst)
    assert len(field_expressions) == 1
    stored_expression = field_expressions[0]
    assert stored_expression["field_name"] == "messages"

    # Get expression_json from GET response (still includes field_expressions array)
    assert "field_expressions" in dst
    assert len(dst["field_expressions"]) == 1
    expression_json = dst["field_expressions"][0]["expression_json"]
    assert expression_json is not None

    # Verify the expression JSON structure
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
                "tool_description": {
                    "name": "Test Tool",
                    "description": "d",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "component_name": "LLM Call",
                "component_description": "Templated LLM Call",
                "parameters": [
                    {
                        "name": "prompt_template",
                        "value": expression_text,
                        "kind": ParameterKind.INPUT,
                        "order": None,
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


def test_deploy_remaps_field_expression_instance_ids():
    """Deploy should remap instance IDs in field expressions to new IDs."""
    project_id, endpoint = _create_project_and_get_endpoint("deploy_expr")

    src_instance_id = str(uuid4())
    dst_instance_id = str(uuid4())
    edge_id = str(uuid4())
    expression_text = f"Task: @{{{{{src_instance_id}.output}}}} - Sources: @{{{{{src_instance_id}.artifacts::docs}}}}"

    payload = _create_graph_payload_with_field_expressions(
        src_instance_id=src_instance_id,
        dst_instance_id=dst_instance_id,
        edge_id=edge_id,
        expression_text=expression_text,
    )

    put_resp = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert put_resp.status_code == 200

    deploy_resp = client.post(f"{endpoint}/deploy", headers=HEADERS_JWT)
    assert deploy_resp.status_code == 200
    deploy_data = deploy_resp.json()
    new_draft_graph_runner_id = deploy_data["draft_graph_runner_id"]

    new_draft_endpoint = f"/projects/{project_id}/graph/{new_draft_graph_runner_id}"
    get_resp = client.get(new_draft_endpoint, headers=HEADERS_JWT)
    assert get_resp.status_code == 200
    new_graph = get_resp.json()

    target_instance = next(ci for ci in new_graph["component_instances"] if ci["name"] == "Target Agent")
    field_expressions = _get_field_expressions_from_instance(target_instance)
    assert len(field_expressions) == 1

    expr_text = field_expressions[0]["expression_text"]
    # Get expression_json from GET response (still includes field_expressions array)
    assert "field_expressions" in target_instance
    assert len(target_instance["field_expressions"]) == 1
    expr_json = target_instance["field_expressions"][0]["expression_json"]
    assert expr_json is not None

    src_instance_new = next(ci for ci in new_graph["component_instances"] if ci["name"] == "Source Agent")
    new_src_id = src_instance_new["id"]

    _assert_expression_remapped(expr_json, expr_text, src_instance_id, new_src_id)

    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)


def test_load_copy_includes_field_expressions_and_roundtrip():
    """load-copy should include field expressions and remap refs to new IDs, and its payload should PUT cleanly."""
    project_id, endpoint = _create_project_and_get_endpoint("load_copy_expr")

    src_instance_id = str(uuid4())
    dst_instance_id = str(uuid4())
    edge_id = str(uuid4())
    expression_text = f"Task: @{{{{{src_instance_id}.output}}}} - Style: @{{{{{src_instance_id}.output}}}}"

    payload = _create_graph_payload_with_field_expressions(
        src_instance_id=src_instance_id,
        dst_instance_id=dst_instance_id,
        edge_id=edge_id,
        expression_text=expression_text,
    )

    put_resp = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert put_resp.status_code == 200

    # GET load-copy
    load_copy_resp = client.get(f"{endpoint}/load-copy", headers=HEADERS_JWT)
    assert load_copy_resp.status_code == 200
    load_payload = load_copy_resp.json()

    # Ensure we have two instances and new IDs
    assert len(load_payload["component_instances"]) == 2
    new_src = next(ci for ci in load_payload["component_instances"] if ci["name"] == "Source Agent")
    new_dst = next(ci for ci in load_payload["component_instances"] if ci["name"] == "Target Agent")
    assert new_src["id"] != src_instance_id
    assert new_dst["id"] != dst_instance_id

    # Field expressions should be present on new_dst and reference new_src
    field_expressions = _get_field_expressions_from_instance(new_dst)
    assert len(field_expressions) == 1
    expr_text_new = field_expressions[0]["expression_text"]
    assert str(src_instance_id) not in expr_text_new
    assert str(new_src["id"]) in expr_text_new

    project_id_2, clone_endpoint = _create_project_and_get_endpoint("load_copy_expr_target")
    clone_put = client.put(clone_endpoint, headers=HEADERS_JWT, json=load_payload)
    assert clone_put.status_code == 200

    # Verify cloned graph has the expressions
    clone_get = client.get(clone_endpoint, headers=HEADERS_JWT)
    assert clone_get.status_code == 200
    cloned = clone_get.json()
    cloned_dst = next(ci for ci in cloned["component_instances"] if ci["name"] == "Target Agent")
    field_expressions = _get_field_expressions_from_instance(cloned_dst)
    assert len(field_expressions) == 1

    # Cleanup
    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)
    client.delete(f"/projects/{project_id_2}", headers=HEADERS_JWT)


def test_load_copy_cloned_graph_has_remapped_field_expressions():
    """After PUT load-copy payload, the cloned graph should have field expressions with remapped IDs."""
    project_id, endpoint = _create_project_and_get_endpoint("load_copy_clone")

    src_instance_id = str(uuid4())
    dst_instance_id = str(uuid4())
    edge_id = str(uuid4())
    expression_text = f"Task: @{{{{{src_instance_id}.output}}}} - Sources: @{{{{{src_instance_id}.artifacts::docs}}}}"

    payload = _create_graph_payload_with_field_expressions(
        src_instance_id=src_instance_id,
        dst_instance_id=dst_instance_id,
        edge_id=edge_id,
        expression_text=expression_text,
    )

    put_resp = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert put_resp.status_code == 200

    load_copy_resp = client.get(f"{endpoint}/load-copy", headers=HEADERS_JWT)
    assert load_copy_resp.status_code == 200
    load_payload = load_copy_resp.json()

    project_id_clone, clone_endpoint = _create_project_and_get_endpoint("load_copy_clone_target")
    clone_put = client.put(clone_endpoint, headers=HEADERS_JWT, json=load_payload)
    assert clone_put.status_code == 200

    clone_get = client.get(clone_endpoint, headers=HEADERS_JWT)
    assert clone_get.status_code == 200
    cloned_graph = clone_get.json()

    cloned_src = next(ci for ci in cloned_graph["component_instances"] if ci["name"] == "Source Agent")
    cloned_dst = next(ci for ci in cloned_graph["component_instances"] if ci["name"] == "Target Agent")
    cloned_src_id = cloned_src["id"]

    field_expressions = _get_field_expressions_from_instance(cloned_dst)
    assert len(field_expressions) == 1

    cloned_expr_text = field_expressions[0]["expression_text"]
    # Get expression_json from GET response (still includes field_expressions array)
    assert "field_expressions" in cloned_dst
    assert len(cloned_dst["field_expressions"]) == 1
    cloned_expr_json = cloned_dst["field_expressions"][0]["expression_json"]
    assert cloned_expr_json is not None

    _assert_expression_remapped(
        cloned_expr_json, cloned_expr_text, src_instance_id, cloned_src_id, context="Cloned graph: "
    )

    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)
    client.delete(f"/projects/{project_id_clone}", headers=HEADERS_JWT)


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
                "tool_description": {
                    "name": "Test Tool",
                    "description": "d",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "component_name": "LLM Call",
                "component_description": "Templated LLM Call",
                "parameters": [
                    {
                        "name": "prompt_template",
                        "value": expression_text,
                        "kind": ParameterKind.INPUT,
                        "order": None,
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
