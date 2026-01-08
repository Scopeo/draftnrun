# flake8: noqa: E501
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.database.setup_db import SessionLocal
from ada_backend.main import app
from ada_backend.repositories.graph_runner_repository import delete_graph_runner
from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings

# Test constants
SOURCE_PORT_NAME = "output"
TARGET_PORT_NAME = "messages"

client = TestClient(app)
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"  # umbrella organization
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}
COMPONENT_ID = str(COMPONENT_UUIDS["llm_call"])
COMPONENT_VERSION_ID = str(COMPONENT_VERSION_UUIDS["llm_call"])


def test_get_put_roundtrip_port_mappings_migration():
    """
    For an unmigrated graph (no port_mappings provided on PUT), verify that:
    - PUT succeeds
    - GET returns explicit auto-generated port_mappings
    - Using that GET payload (minus non-updatable fields) on PUT works (idempotent)
    - Subsequent GET returns the same explicit port_mappings
    """
    # Create a unique project for this test to avoid constraint violations
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"port_mappings_test_{project_id}",
        "description": "Test project for port mappings migration",
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
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [
                    {
                        "value": "Reformulate the question as a customer service query :\n{input}",
                        "name": "prompt_template",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "Answer this question: {input}",
                        "ui_component": "Textarea",
                        "ui_component_properties": {
                            "label": "Prompt Template",
                            "placeholder": "Enter the prompt here. Use {input} (or similar) to insert dynamic content -  the {} braces with a keyword are mandatory.",
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
                            ],
                        },
                        "is_advanced": False,
                    },
                    {
                        "value": 1,
                        "name": "default_temperature",
                        "order": None,
                        "id": "5bdece0d-bbc1-4cc7-a192-c4b7298dc163",
                        "type": "float",
                        "nullable": False,
                        "default": "1.0",
                        "ui_component": "Slider",
                        "ui_component_properties": {
                            "label": "Temperature",
                            "placeholder": "Enter temperature, it is different for each model, check the model documentation",
                            "min": 0,
                            "max": 2,
                            "step": 0.01,
                            "marks": True,
                        },
                        "is_advanced": True,
                    },
                ],
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
                            "placeholder": "Enter the prompt here. Use {input} (or similar) to insert dynamic content -  the {} braces with a keyword are mandatory.",
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
                            ],
                        },
                        "is_advanced": False,
                    },
                    {
                        "value": 1,
                        "name": "default_temperature",
                        "order": None,
                        "id": "5bdece0d-bbc1-4cc7-a192-c4b7298dc163",
                        "type": "float",
                        "nullable": False,
                        "default": "1.0",
                        "ui_component": "Slider",
                        "ui_component_properties": {
                            "label": "Temperature",
                            "placeholder": "Enter temperature, it is different for each model, check the model documentation",
                            "min": 0,
                            "max": 2,
                            "step": 0.01,
                            "marks": True,
                        },
                        "is_advanced": True,
                    },
                ],
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
    assert pm["target_port_name"] == "messages"
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

    # Cleanup this graph runner and project
    session = SessionLocal()
    try:
        delete_graph_runner(session, UUID(graph_runner_id))
    finally:
        session.close()
    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)


def test_deploy_graph_copies_port_mappings():
    """
    Test that when deploying a graph, the port mappings are correctly copied
    to the new graph runner.
    """
    # Create a unique project for this test to avoid constraint violations
    project_id = str(uuid4())
    project_payload = {
        "project_id": project_id,
        "project_name": f"deploy_port_mappings_test_{project_id}",
        "description": "Test project for deploy port mappings",
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

    # Two component instances connected by a single edge with explicit port mappings
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
                "component_id": COMPONENT_ID,
                "component_version_id": COMPONENT_VERSION_ID,
                "parameters": [
                    {
                        "value": "Reformulate the question as a customer service query :\n{input}",
                        "name": "prompt_template",
                        "order": None,
                        "type": "string",
                        "nullable": False,
                        "default": "Answer this question: {input}",
                        "ui_component": "Textarea",
                        "ui_component_properties": {
                            "label": "Prompt Template",
                            "placeholder": "Enter the prompt here. Use {input} (or similar) to insert dynamic content -  the {} braces with a keyword are mandatory.",
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
                            ],
                        },
                        "is_advanced": False,
                    },
                    {
                        "value": 1,
                        "name": "default_temperature",
                        "order": None,
                        "id": "5bdece0d-bbc1-4cc7-a192-c4b7298dc163",
                        "type": "float",
                        "nullable": False,
                        "default": "1.0",
                        "ui_component": "Slider",
                        "ui_component_properties": {
                            "label": "Temperature",
                            "placeholder": "Enter temperature, it is different for each model, check the model documentation",
                            "min": 0,
                            "max": 2,
                            "step": 0.01,
                            "marks": True,
                        },
                        "is_advanced": True,
                    },
                ],
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
                            "placeholder": "Enter the prompt here. Use {input} (or similar) to insert dynamic content -  the {} braces with a keyword are mandatory.",
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
                            ],
                        },
                        "is_advanced": False,
                    },
                    {
                        "value": 1,
                        "name": "default_temperature",
                        "order": None,
                        "id": "5bdece0d-bbc1-4cc7-a192-c4b7298dc163",
                        "type": "float",
                        "nullable": False,
                        "default": "1.0",
                        "ui_component": "Slider",
                        "ui_component_properties": {
                            "label": "Temperature",
                            "placeholder": "Enter temperature, it is different for each model, check the model documentation",
                            "min": 0,
                            "max": 2,
                            "step": 0.01,
                            "marks": True,
                        },
                        "is_advanced": True,
                    },
                ],
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
        "port_mappings": [
            {
                "source_instance_id": src_instance_id,
                "source_port_name": SOURCE_PORT_NAME,
                "target_instance_id": dst_instance_id,
                "target_port_name": TARGET_PORT_NAME,
                "dispatch_strategy": "direct",
            }
        ],
    }

    # Create the graph with explicit port mappings
    put_resp = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["graph_id"] == graph_runner_id

    # Verify the original graph has the port mappings
    get_resp = client.get(endpoint, headers=HEADERS_JWT)
    assert get_resp.status_code == 200
    original_data = get_resp.json()
    assert "port_mappings" in original_data
    assert len(original_data["port_mappings"]) == 1
    original_pm = original_data["port_mappings"][0]
    assert original_pm["source_port_name"] == SOURCE_PORT_NAME
    assert original_pm["target_port_name"] == TARGET_PORT_NAME

    # Deploy the graph
    deploy_resp = client.post(f"{endpoint}/deploy", headers=HEADERS_JWT)
    assert deploy_resp.status_code == 200
    deploy_data = deploy_resp.json()

    # The deploy should return both the new draft graph and the production graph
    assert "draft_graph_runner_id" in deploy_data
    assert "prod_graph_runner_id" in deploy_data
    assert deploy_data["prod_graph_runner_id"] == graph_runner_id

    new_draft_graph_id = deploy_data["draft_graph_runner_id"]

    # Verify the new draft graph has the same port mappings (with updated instance IDs)
    new_draft_endpoint = f"/projects/{project_id}/graph/{new_draft_graph_id}"
    new_get_resp = client.get(new_draft_endpoint, headers=HEADERS_JWT)
    assert new_get_resp.status_code == 200
    new_data = new_get_resp.json()

    assert "port_mappings" in new_data
    assert len(new_data["port_mappings"]) == 1
    new_pm = new_data["port_mappings"][0]

    # The port mapping should have the same structure but different instance IDs
    assert new_pm["source_port_name"] == SOURCE_PORT_NAME
    assert new_pm["target_port_name"] == TARGET_PORT_NAME
    assert new_pm["dispatch_strategy"] == "direct"

    # The instance IDs should be different (new instances were created)
    assert new_pm["source_instance_id"] != src_instance_id
    assert new_pm["target_instance_id"] != dst_instance_id

    # Verify the production graph also has the port mappings
    prod_get_resp = client.get(endpoint, headers=HEADERS_JWT)
    assert prod_get_resp.status_code == 200
    prod_data = prod_get_resp.json()
    assert "port_mappings" in prod_data
    assert len(prod_data["port_mappings"]) == 1
    prod_pm = prod_data["port_mappings"][0]
    assert prod_pm["source_port_name"] == SOURCE_PORT_NAME
    assert prod_pm["target_port_name"] == TARGET_PORT_NAME

    # Cleanup both graph runners and project
    session = SessionLocal()
    try:
        delete_graph_runner(session, UUID(graph_runner_id))
        delete_graph_runner(session, UUID(new_draft_graph_id))
    finally:
        session.close()
    client.delete(f"/projects/{project_id}", headers=HEADERS_JWT)
