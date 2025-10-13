import json
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

# JSON constants for test workflow configuration
DEFAULT_PAYLOAD_SCHEMA = {"messages": [{"role": "user", "content": "Hello"}], "additional_info": "info"}

DEFAULT_FILTER_SCHEMA = {
    "type": "object",
    "title": "AgentPayload",
    "properties": {
        "messages": {
            "type": "array",
            "items": {
                "type": "ChatMessage",
                "properties": {
                    "role": {"type": "string"},
                    "content": {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
                    "tool_calls": {"type": "array", "items": {"type": "object"}},
                    "tool_call_id": {"type": "string"},
                },
                "required": ["role"],
            },
        },
        "error": {"type": "string"},
        "artifacts": {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "title": "SourceChunk",
                        "properties": {
                            "name": {"type": "string"},
                            "document_name": {"type": "string"},
                            "content": {"type": "string"},
                            "url": {"type": "string"},
                            "url_display_type": {
                                "type": "string",
                                "enum": ["blank", "download", "viewer", "no_show"],
                                "default": "viewer",
                            },
                            "metadata": {"type": "object", "additionalProperties": True},
                        },
                        "required": ["name", "document_name", "content"],
                    },
                }
            },
            "additionalProperties": True,
        },
        "is_final": {"type": "boolean"},
    },
    "required": ["messages"],
}


def test_version_management():
    """Test that projects no longer create default versions."""
    # Create a project
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"version_test_{project_uuid}",
        "description": "Test project for version management",
    }

    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    # Verify that version endpoints no longer exist (should return 404 because the endpoint doesn't exist)
    versions_response = client.get(f"/projects/{project_uuid}/qa/versions", headers=HEADERS_JWT)
    assert versions_response.status_code == 404  # Not Found - endpoint doesn't exist

    # Cleanup
    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_dataset_management():
    """Test dataset CRUD operations."""

    # Create a project
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"dataset_test_{project_uuid}",
        "description": "Test project for dataset management",
    }

    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    # Test dataset creation
    dataset_endpoint = f"/projects/{project_uuid}/qa/datasets"
    create_payload = {"datasets_name": ["dataset1", "dataset2", "dataset3"]}

    create_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=create_payload)
    assert create_response.status_code == 200
    created_datasets = create_response.json()["datasets"]
    assert len(created_datasets) == 3

    # Test dataset retrieval
    get_response = client.get(dataset_endpoint, headers=HEADERS_JWT)
    assert get_response.status_code == 200
    retrieved_datasets = get_response.json()
    assert len(retrieved_datasets) == 3

    # Test dataset update
    dataset_to_update = created_datasets[0]["id"]
    update_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_to_update}?dataset_name=updated_dataset1"

    update_response = client.patch(update_endpoint, headers=HEADERS_JWT)
    assert update_response.status_code == 200
    updated_dataset = update_response.json()
    assert updated_dataset["dataset_name"] == "updated_dataset1"

    # Test dataset deletion
    dataset_to_delete = created_datasets[1]["id"]
    delete_payload = {"dataset_ids": [dataset_to_delete]}

    delete_response = client.request(method="DELETE", url=dataset_endpoint, headers=HEADERS_JWT, json=delete_payload)
    assert delete_response.status_code == 200
    delete_result = delete_response.json()
    assert "message" in delete_result
    assert "1" in delete_result["message"]  # Should have deleted 1 dataset

    # Verify the dataset was deleted
    get_response = client.get(dataset_endpoint, headers=HEADERS_JWT)
    assert get_response.status_code == 200
    remaining_datasets = get_response.json()
    assert len(remaining_datasets) == 2  # Should now have 2 datasets instead of 3

    # Cleanup
    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_input_groundtruth_basic_operations():
    """Test input-groundtruth CRUD operations."""

    # Create a project
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"input_groundtruth_test_{project_uuid}",
        "description": "Test project for input-groundtruth operations",
    }

    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    # Create a dataset
    dataset_uuid = str(uuid4())
    dataset_payload = {"datasets_name": [f"input_groundtruth_dataset_{dataset_uuid}"]}

    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_data = dataset_response.json()
    dataset_id = dataset_data["datasets"][0]["id"]

    # Test input-groundtruth creation
    input_endpoint = f"/projects/{project_uuid}/qa/{dataset_id}/entries"
    create_payload = {
        "inputs_groundtruths": [
            {"input": "What is 2 + 2?", "groundtruth": "4"},
            {"input": "What is the capital of France?", "groundtruth": "Paris"},
            {"input": "What is the weather like today?"},  # No groundtruth
        ]
    }

    create_response = client.post(input_endpoint, headers=HEADERS_JWT, json=create_payload)
    assert create_response.status_code == 200
    created_inputs = create_response.json()["inputs_groundtruths"]
    assert len(created_inputs) == 3

    # Test input-groundtruth retrieval
    get_response = client.get(input_endpoint, headers=HEADERS_JWT)
    assert get_response.status_code == 200
    retrieved_inputs = get_response.json()["inputs_groundtruths"]
    assert len(retrieved_inputs) == 3

    # Test input-groundtruth update
    input_to_update = created_inputs[0]["id"]
    update_payload = {
        "inputs_groundtruths": [{"id": input_to_update, "input": "What is 2 + 2?", "groundtruth": "4 (updated)"}]
    }

    update_response = client.patch(input_endpoint, headers=HEADERS_JWT, json=update_payload)
    assert update_response.status_code == 200
    updated_inputs = update_response.json()["inputs_groundtruths"]
    assert len(updated_inputs) == 1
    assert updated_inputs[0]["groundtruth"] == "4 (updated)"

    # Test input-groundtruth deletion
    input_to_delete = created_inputs[1]["id"]
    delete_payload = {"input_groundtruth_ids": [input_to_delete]}

    delete_response = client.request(method="DELETE", url=input_endpoint, headers=HEADERS_JWT, json=delete_payload)
    assert delete_response.status_code == 200
    delete_result = delete_response.json()
    assert "message" in delete_result
    assert "1" in delete_result["message"]  # Should have deleted 1 input

    # Verify the input was deleted
    get_response = client.get(input_endpoint, headers=HEADERS_JWT)
    assert get_response.status_code == 200
    remaining_inputs = get_response.json()["inputs_groundtruths"]
    assert len(remaining_inputs) == 2  # Should now have 2 inputs instead of 3

    # Cleanup
    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def _create_dummy_agent_workflow_config():
    """Helper function to create the dummy agent workflow configuration."""
    # Create dummy UUIDs for the workflow components
    api_input_id = str(uuid4())
    filter_id = str(uuid4())
    edge_id = str(uuid4())

    return {
        "component_instances": [
            {
                "is_agent": True,
                "is_protected": True,
                "function_callable": False,
                "can_use_function_calling": False,
                "release_stage": "beta",
                "tool_parameter_name": None,
                "subcomponents_info": [],
                "id": api_input_id,
                "name": "API Input",
                "ref": "API Input",
                "is_start_node": True,
                "component_id": "01357c0b-bc99-44ce-a435-995acc5e2544",  # input component UUID
                "parameters": [
                    {
                        "value": DEFAULT_PAYLOAD_SCHEMA,
                        "name": "payload_schema",
                        "order": None,
                        "id": "48332255-4a0e-4432-8fb4-46267e8ffd4d",
                        "type": "string",
                        "nullable": False,
                        "default": DEFAULT_PAYLOAD_SCHEMA,
                        "ui_component": "Textarea",
                        "ui_component_properties": {
                            "label": "An exemple of your payload schema",
                            "description": "Give here an example of the payload schema "
                            "of your input for the workflow. Must be a correct json. "
                            "The keys of this dictonary can be referenced in the next components"
                            " as variables, for example: {{additional_info}}",
                        },
                        "is_advanced": False,
                    }
                ],
                "tool_description": {
                    "name": "default",
                    "description": "",
                    "tool_properties": {},
                    "required_tool_properties": [],
                },
                "integration": None,
                "component_name": "API Input",
                "component_description": "This block is triggered by an API call",
            },
            {
                "is_agent": True,
                "is_protected": True,
                "function_callable": False,
                "can_use_function_calling": False,
                "release_stage": "beta",
                "tool_parameter_name": None,
                "subcomponents_info": [],
                "id": filter_id,
                "name": "Filter",
                "ref": "Filter",
                "is_start_node": False,
                "component_id": "02468c0b-bc99-44ce-a435-995acc5e2545",  # filter component UUID
                "parameters": [
                    {
                        "value": DEFAULT_FILTER_SCHEMA,
                        "name": "filtering_json_schema",
                        "order": None,
                        "id": "59443366-5b1f-5543-9fc5-57378f9aaf6e",
                        "type": "string",
                        "nullable": False,
                        "default": DEFAULT_FILTER_SCHEMA,
                        "ui_component": "Textarea",
                        "ui_component_properties": {
                            "label": "Filtering schema to apply",
                            "description": "Describe here the schema for filtering "
                            "the final workflow response. Must be a correct json schema."
                            " The output will be validated against this schema and "
                            "filtered to only include the specified fields.",
                        },
                        "is_advanced": False,
                    }
                ],
                "tool_description": {
                    "name": "Filter_Tool",
                    "description": "An filter tool that filters the input data to return an AgentPayload.",
                    "tool_properties": {"input_data": {"type": "json", "description": "An filter tool"}},
                    "required_tool_properties": [],
                },
                "integration": None,
                "component_name": "Filter",
                "component_description": "Filter: takes a json and filters it according to a given json schema",
            },
        ],
        "relationships": [],
        "edges": [{"id": edge_id, "origin": api_input_id, "destination": filter_id, "order": 0}],
        "port_mappings": [
            {
                "source_instance_id": api_input_id,
                "source_port_name": "messages",
                "target_instance_id": filter_id,
                "target_port_name": "messages",
            }
        ],
    }


def test_run_qa_endpoint():
    """Test the run_qa endpoint with a configured workflow."""

    # Create a project for testing
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"qa_run_test_{project_uuid}",
        "description": "Test project for QA run endpoint",
    }

    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200
    project_data = project_response.json()
    assert project_data["project_id"] == project_uuid

    # Get the project details to find the graph runner ID
    project_details_response = client.get(f"/projects/{project_uuid}", headers=HEADERS_JWT)
    assert project_details_response.status_code == 200
    project_details = project_details_response.json()

    # Find the draft graph runner
    draft_graph_runner = None
    for gr in project_details["graph_runners"]:
        if gr["env"] == "draft":
            draft_graph_runner = gr
            break

    assert draft_graph_runner is not None, "Draft graph runner not found"
    graph_runner_id = draft_graph_runner["graph_runner_id"]

    # Update the project's workflow configuration using the helper function
    workflow_config = _create_dummy_agent_workflow_config()

    # Update the graph
    update_graph_response = client.put(
        f"/projects/{project_uuid}/graph/{graph_runner_id}", headers=HEADERS_JWT, json=workflow_config
    )
    assert update_graph_response.status_code == 200

    # Deploy the project to production so we can test the production version
    deploy_response = client.post(f"/projects/{project_uuid}/graph/{graph_runner_id}/deploy", headers=HEADERS_JWT)
    assert deploy_response.status_code == 200

    # Create a dataset
    dataset_uuid = str(uuid4())
    dataset_payload = {"datasets_name": [f"qa_run_dataset_{dataset_uuid}"]}

    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_data = dataset_response.json()
    dataset_id = dataset_data["datasets"][0]["id"]

    # Create input-groundtruth entries
    input_payload = {
        "inputs_groundtruths": [
            {"input": "What is 2 + 2?", "groundtruth": "4"},
            {"input": "What is the capital of France?", "groundtruth": "Paris"},
            {"input": "What is the weather like today?"},  # No groundtruth
        ]
    }

    input_response = client.post(
        f"/projects/{project_uuid}/qa/{dataset_id}/entries", headers=HEADERS_JWT, json=input_payload
    )
    assert input_response.status_code == 200
    input_data = input_response.json()
    assert len(input_data["inputs_groundtruths"]) == 3

    # Test the run_qa endpoint with draft version on selected inputs
    run_qa_payload_selection = {
        "version": "draft",
        "input_ids": [input_data["inputs_groundtruths"][0]["id"], input_data["inputs_groundtruths"][1]["id"]],
    }

    run_qa_response_selection = client.post(
        f"/projects/{project_uuid}/qa/{dataset_id}/run", headers=HEADERS_JWT, json=run_qa_payload_selection
    )

    assert (
        run_qa_response_selection.status_code == 200
    ), f"Expected status code 200, got {run_qa_response_selection.status_code}"

    qa_results_selection = run_qa_response_selection.json()
    assert "results" in qa_results_selection
    assert "summary" in qa_results_selection

    # Check that all results ran successfully
    # Note: The dummy workflow (API Input → Filter) uses a static payload_schema parameter
    # rather than echoing the runtime input, so we just verify execution succeeded
    for result in qa_results_selection["results"]:
        output_content = json.loads(result["output"])[0]["content"]
        assert result["success"] is True, f"All results should be successful. Result: {result}"
        assert result["version"] == "draft", f"Version should be draft. Result: {result}"
        assert isinstance(output_content, str), f"Output content should be a string. Got: {output_content}"

    # Verify summary statistics for selection
    summary_selection = qa_results_selection["summary"]
    assert summary_selection["total"] == 2
    assert summary_selection["passed"] == 2
    assert summary_selection["failed"] == 0
    assert summary_selection["success_rate"] == 100.0

    # Test the run_qa endpoint with run_all=True on production version
    run_qa_payload_all = {
        "version": "production",
        "run_all": True,
    }

    run_qa_response_all = client.post(
        f"/projects/{project_uuid}/qa/{dataset_id}/run", headers=HEADERS_JWT, json=run_qa_payload_all
    )

    assert run_qa_response_all.status_code == 200, f"Expected status code 200, got {run_qa_response_all.status_code}"

    qa_results_all = run_qa_response_all.json()
    assert "results" in qa_results_all
    assert "summary" in qa_results_all

    # Should process all 3 entries when using run_all=True
    assert len(qa_results_all["results"]) == 3

    # Check that all results ran successfully
    # Note: The dummy workflow (API Input → Filter) uses a static payload_schema parameter
    # rather than echoing the runtime input, so we just verify execution succeeded
    for result in qa_results_all["results"]:
        output_content = json.loads(result["output"])[0]["content"]
        assert result["success"] is True, f"All results should be successful. Result: {result}"
        assert result["version"] == "production", f"Version should be production. Result: {result}"
        assert isinstance(output_content, str), f"Output content should be a string. Got: {output_content}"

    # Verify summary statistics for run_all
    summary_all = qa_results_all["summary"]
    assert summary_all["total"] == 3
    assert summary_all["passed"] == 3
    assert summary_all["failed"] == 0
    assert summary_all["success_rate"] == 100.0

    # Cleanup
    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_quality_assurance_complete_workflow():
    """Test a complete quality assurance workflow."""

    # Create a project
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"qa_complete_workflow_{project_uuid}",
        "description": "Test project for complete QA workflow",
    }

    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    # Create a dataset
    dataset_payload = {"datasets_name": ["complete_workflow_dataset"]}
    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    # Create input-groundtruth entries
    input_payload = {
        "inputs_groundtruths": [
            {"input": "Test input 1", "groundtruth": "Expected output 1"},
            {"input": "Test input 2", "groundtruth": "Expected output 2"},
        ]
    }
    input_response = client.post(
        f"/projects/{project_uuid}/qa/{dataset_id}/entries", headers=HEADERS_JWT, json=input_payload
    )
    assert input_response.status_code == 200
    input_data = input_response.json()

    # Test querying without version filter - should return all entries with null versions initially
    get_response_initial = client.get(f"/projects/{project_uuid}/qa/{dataset_id}/entries", headers=HEADERS_JWT)
    assert get_response_initial.status_code == 200
    initial_results = get_response_initial.json()["inputs_groundtruths"]
    assert len(initial_results) == 2  # All 2 inputs should be returned
    # All should have no outputs initially (LEFT JOIN behavior)
    for result in initial_results:
        assert result["output"] is None
        assert result["version"] is None
        assert result["input_id"] is not None
        assert result["input"] is not None
        assert result["groundtruth"] is not None

    # Test filtering by version (draft) - should return 0 results initially
    get_response_draft = client.get(
        f"/projects/{project_uuid}/qa/{dataset_id}/entries?version=draft", headers=HEADERS_JWT
    )
    assert get_response_draft.status_code == 200
    draft_results = get_response_draft.json()["inputs_groundtruths"]
    assert len(draft_results) == 0  # No draft outputs exist yet

    # Run QA on draft version
    run_qa_payload = {
        "version": "draft",
        "input_ids": [input_data["inputs_groundtruths"][0]["id"]],
    }
    run_qa_response = client.post(
        f"/projects/{project_uuid}/qa/{dataset_id}/run", headers=HEADERS_JWT, json=run_qa_payload
    )
    assert run_qa_response.status_code == 200

    # Check that draft version outputs now exist
    get_response_draft_after = client.get(
        f"/projects/{project_uuid}/qa/{dataset_id}/entries?version=draft", headers=HEADERS_JWT
    )
    assert get_response_draft_after.status_code == 200
    draft_results_after = get_response_draft_after.json()["inputs_groundtruths"]
    # Should return exactly 1 result with draft version output
    assert len(draft_results_after) == 1
    assert draft_results_after[0]["version"] == "draft"
    assert draft_results_after[0]["output"] is not None

    # Run QA on production version
    run_qa_payload_production = {
        "version": "production",
        "input_ids": [input_data["inputs_groundtruths"][1]["id"]],
    }
    run_qa_response_production = client.post(
        f"/projects/{project_uuid}/qa/{dataset_id}/run", headers=HEADERS_JWT, json=run_qa_payload_production
    )
    assert run_qa_response_production.status_code == 200

    # Check that production version outputs now exist
    get_response_production = client.get(
        f"/projects/{project_uuid}/qa/{dataset_id}/entries?version=production", headers=HEADERS_JWT
    )
    assert get_response_production.status_code == 200
    production_results = get_response_production.json()["inputs_groundtruths"]
    # Should return exactly 1 result with production version output
    assert len(production_results) == 1
    assert production_results[0]["version"] == "production"
    assert production_results[0]["output"] is not None

    # Check that getting all versions shows both draft and production outputs
    get_response_all = client.get(f"/projects/{project_uuid}/qa/{dataset_id}/entries", headers=HEADERS_JWT)
    assert get_response_all.status_code == 200
    all_results = get_response_all.json()["inputs_groundtruths"]
    assert len(all_results) == 2
    versions_found = [r["version"] for r in all_results if r["version"] is not None]
    assert "draft" in versions_found
    assert "production" in versions_found

    # Cleanup
    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)
