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
    """Test creating and managing multiple versions."""
    # Create a project
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"version_test_{project_uuid}",
        "description": "Test project for version management",
    }

    project_response = client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200

    # Verify default version was created
    versions_response = client.get(f"/projects/{project_uuid}/qa/versions", headers=HEADERS_JWT)
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert len(versions) == 1
    assert versions[0]["version"] == "0.0.1"

    # Create additional versions
    create_versions_response = client.post(
        f"/projects/{project_uuid}/qa/versions", headers=HEADERS_JWT, json={"versions": ["1.0.0", "1.1.0"]}
    )
    assert create_versions_response.status_code == 200

    # Verify all versions exist
    versions_response = client.get(f"/projects/{project_uuid}/qa/versions", headers=HEADERS_JWT)
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert len(versions) == 3
    version_strings = [v["version"] for v in versions]
    assert "0.0.1" in version_strings
    assert "1.0.0" in version_strings
    assert "1.1.0" in version_strings

    # Test version deletion - delete one version
    version_to_delete = "1.0.0"
    version_to_delete_id = None
    for version in versions:
        if version["version"] == version_to_delete:
            version_to_delete_id = version["id"]
            break
    assert version_to_delete_id is not None, f"Version {version_to_delete} not found"
    delete_payload = {"version_ids": [version_to_delete_id]}
    delete_response = client.request(
        method="DELETE", url=f"/projects/{project_uuid}/qa/versions", headers=HEADERS_JWT, json=delete_payload
    )
    assert delete_response.status_code == 200
    delete_result = delete_response.json()
    assert "message" in delete_result
    assert "1" in delete_result["message"]  # Should have deleted 1 version

    # Verify the version was deleted
    versions_response = client.get(f"/projects/{project_uuid}/qa/versions", headers=HEADERS_JWT)
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert len(versions) == 2  # Should now have 2 versions instead of 3

    # Verify the correct version was deleted
    remaining_version_strings = [v["version"] for v in versions]
    assert "0.0.1" in remaining_version_strings
    assert "1.1.0" in remaining_version_strings
    assert "1.0.0" not in remaining_version_strings  # This version should be gone

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
    create_payload = {"datasets": ["dataset1", "dataset2", "dataset3"]}

    create_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=create_payload)
    assert create_response.status_code == 200
    created_datasets = create_response.json()["datasets"]
    assert len(created_datasets) == 3

    # Test dataset retrieval
    get_response = client.get(dataset_endpoint, headers=HEADERS_JWT)
    assert get_response.status_code == 200
    datasets = get_response.json()
    assert len(datasets) == 3

    # Test dataset update
    dataset_to_update = created_datasets[0]
    update_payload = {"datasets": [{"id": dataset_to_update["id"], "dataset_name": "updated_dataset1"}]}

    update_response = client.patch(dataset_endpoint, headers=HEADERS_JWT, json=update_payload)
    assert update_response.status_code == 200
    updated_datasets = update_response.json()["datasets"]
    assert updated_datasets[0]["dataset_name"] == "updated_dataset1"

    # Test dataset deletion
    delete_payload = {"dataset_ids": [dataset_to_update["id"]]}

    delete_response = client.request(method="DELETE", url=dataset_endpoint, headers=HEADERS_JWT, json=delete_payload)
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Deleted 1 datasets successfully"

    # Verify dataset was deleted
    get_after_delete = client.get(dataset_endpoint, headers=HEADERS_JWT)
    assert get_after_delete.status_code == 200
    remaining_datasets = get_after_delete.json()
    assert len(remaining_datasets) == 2

    # Cleanup
    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_input_groundtruth_basic_operations():
    """Test basic input-groundtruth operations without complex workflow."""

    # Create project and dataset
    project_uuid = str(uuid4())
    project_response = client.post(
        f"/projects/{ORGANIZATION_ID}",
        headers=HEADERS_JWT,
        json={
            "project_id": project_uuid,
            "project_name": f"input_test_{project_uuid}",
            "description": "Test project for input operations",
        },
    )
    assert project_response.status_code == 200

    dataset_response = client.post(
        f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json={"datasets": ["test_dataset"]}
    )
    assert dataset_response.status_code == 200
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    # Test input creation
    input_endpoint = f"/projects/{project_uuid}/qa/{dataset_id}"
    create_payload = {
        "inputs_groundtruths": [
            {"input": "Test question 1", "groundtruth": "Test answer 1"},
            {"input": "Test question 2", "groundtruth": "Test answer 2"},
            {"input": "Test question 3"},  # No groundtruth
        ]
    }

    create_response = client.post(input_endpoint, headers=HEADERS_JWT, json=create_payload)
    assert create_response.status_code == 200
    created_inputs = create_response.json()["inputs_groundtruths"]
    assert len(created_inputs) == 3

    # Test input retrieval
    get_response = client.get(input_endpoint, headers=HEADERS_JWT)
    assert get_response.status_code == 200
    retrieved_inputs = get_response.json()
    assert len(retrieved_inputs) == 3

    # Test input update
    input_to_update = created_inputs[0]
    update_payload = {
        "inputs_groundtruths": [
            {"id": input_to_update["id"], "input": "Updated question", "groundtruth": "Updated answer"}
        ]
    }

    update_response = client.patch(input_endpoint, headers=HEADERS_JWT, json=update_payload)
    assert update_response.status_code == 200
    updated_inputs = update_response.json()["inputs_groundtruths"]
    assert updated_inputs[0]["input"] == "Updated question"
    assert updated_inputs[0]["groundtruth"] == "Updated answer"

    # Test input deletion
    delete_payload = {"input_groundtruth_ids": [input_to_update["id"]]}

    delete_response = client.request(method="DELETE", url=input_endpoint, headers=HEADERS_JWT, json=delete_payload)
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "Deleted 1 input-groundtruth entries successfully"

    # Verify input was deleted
    get_after_delete = client.get(input_endpoint, headers=HEADERS_JWT)
    assert get_after_delete.status_code == 200
    remaining_inputs = get_after_delete.json()
    assert len(remaining_inputs) == 2

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

    # Create a dataset
    dataset_uuid = str(uuid4())
    dataset_payload = {"datasets": [f"qa_run_dataset_{dataset_uuid}"]}

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

    input_response = client.post(f"/projects/{project_uuid}/qa/{dataset_id}", headers=HEADERS_JWT, json=input_payload)
    assert input_response.status_code == 200
    input_data = input_response.json()
    assert len(input_data["inputs_groundtruths"]) == 3

    # Get the version ID
    versions_response = client.get(f"/projects/{project_uuid}/qa/versions", headers=HEADERS_JWT)
    assert versions_response.status_code == 200
    versions_data = versions_response.json()
    assert len(versions_data) == 1
    version_id = versions_data[0]["id"]

    # Test the run_qa endpoint
    run_qa_payload = {
        "version_id": version_id,
        "input_ids": [input_data["inputs_groundtruths"][0]["id"], input_data["inputs_groundtruths"][1]["id"]],
    }

    run_qa_response = client.post(
        f"/projects/{project_uuid}/qa/{dataset_id}/run", headers=HEADERS_JWT, json=run_qa_payload
    )

    assert run_qa_response.status_code == 200, f"Expected status code 200, got {run_qa_response.status_code}"

    qa_results = run_qa_response.json()
    assert "results" in qa_results
    assert "summary" in qa_results

    # Check that all results have input == output (dummy agent behavior)
    for result in qa_results["results"]:
        assert (
            result["input"] == result["output"]
        ), f"Input and output should be the same for dummy agent. Input: {result['input']}, Output: {result['output']}"
        assert result["success"] is True, f"All results should be successful. Result: {result}"

    # Verify summary statistics
    summary = qa_results["summary"]
    assert summary["total"] == 2
    assert summary["passed"] == 2
    assert summary["failed"] == 0
    assert summary["success_rate"] == 100.0

    # Verify the inputs now have version output information
    get_inputs_response = client.get(f"/projects/{project_uuid}/qa/{dataset_id}", headers=HEADERS_JWT)
    assert get_inputs_response.status_code == 200
    retrieved_inputs = get_inputs_response.json()

    # Check that the inputs we ran QA on have version information
    for input_item in retrieved_inputs:
        if input_item["input_id"] in [
            input_data["inputs_groundtruths"][0]["id"],
            input_data["inputs_groundtruths"][1]["id"],
        ]:
            # These should have version information even if the run failed
            assert input_item["version_id"] == version_id
            assert input_item["version"] == "0.0.1"

    # Cleanup
    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_quality_assurance_complete_workflow():
    """Complete end-to-end test of the quality assurance workflow."""

    # Test 1: Create a project and verify version creation
    dummy_project_uuid = str(uuid4())
    project_endpoint = f"/projects/{ORGANIZATION_ID}"
    project_payload = {
        "project_id": dummy_project_uuid,
        "project_name": f"dummy_project_{dummy_project_uuid}",
        "description": "Test project for QA workflow",
    }

    project_response = client.post(project_endpoint, headers=HEADERS_JWT, json=project_payload)
    assert project_response.status_code == 200
    project_data = project_response.json()
    assert project_data["project_id"] == dummy_project_uuid

    # Setup dummy agent workflow configuration
    # Get the project details to find the graph runner ID
    project_details_response = client.get(f"/projects/{dummy_project_uuid}", headers=HEADERS_JWT)
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
        f"/projects/{dummy_project_uuid}/graph/{graph_runner_id}", headers=HEADERS_JWT, json=workflow_config
    )
    assert update_graph_response.status_code == 200

    # Test 1.1: Verify that a version was automatically created
    versions_endpoint = f"/projects/{dummy_project_uuid}/qa/versions"
    versions_response = client.get(versions_endpoint, headers=HEADERS_JWT)
    assert versions_response.status_code == 200
    versions_data = versions_response.json()
    assert len(versions_data) == 1
    assert versions_data[0]["version"] == "0.0.1"
    version_id = versions_data[0]["id"]

    # Test 2: Create a dataset
    dummy_dataset_uuid = str(uuid4())
    dataset_endpoint = f"/projects/{dummy_project_uuid}/qa/datasets"
    dataset_payload = {"datasets": [f"dummy_dataset_{dummy_dataset_uuid}"]}

    dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=dataset_payload)
    assert dataset_response.status_code == 200
    dataset_data = dataset_response.json()
    assert len(dataset_data["datasets"]) == 1
    dataset_id = dataset_data["datasets"][0]["id"]
    assert dataset_data["datasets"][0]["dataset_name"] == f"dummy_dataset_{dummy_dataset_uuid}"

    # Test 3: Update dataset name
    dummy_dataset_2_uuid = str(uuid4())
    update_dataset_payload = {
        "datasets": [{"id": dataset_id, "dataset_name": f"dummy_dataset_2_{dummy_dataset_2_uuid}"}]
    }

    update_dataset_response = client.patch(dataset_endpoint, headers=HEADERS_JWT, json=update_dataset_payload)
    assert update_dataset_response.status_code == 200
    updated_dataset_data = update_dataset_response.json()
    assert updated_dataset_data["datasets"][0]["dataset_name"] == f"dummy_dataset_2_{dummy_dataset_2_uuid}"

    # Test 4: Create 3 input-groundtruth entries (2 with groundtruth, 1 without)
    input_endpoint = f"/projects/{dummy_project_uuid}/qa/{dataset_id}"
    input_payload = {
        "inputs_groundtruths": [
            {"input": "What is 2 + 2?", "groundtruth": "4"},
            {"input": "What is the capital of France?", "groundtruth": "Paris"},
            {"input": "What is the weather like today?"},  # No groundtruth
        ]
    }

    input_response = client.post(input_endpoint, headers=HEADERS_JWT, json=input_payload)
    assert input_response.status_code == 200
    input_data = input_response.json()
    assert len(input_data["inputs_groundtruths"]) == 3

    # Verify the inputs were created correctly
    first_input = input_data["inputs_groundtruths"][0]
    second_input = input_data["inputs_groundtruths"][1]
    third_input = input_data["inputs_groundtruths"][2]

    assert first_input["input"] == "What is 2 + 2?"
    assert first_input["groundtruth"] == "4"
    assert second_input["input"] == "What is the capital of France?"
    assert second_input["groundtruth"] == "Paris"
    assert third_input["input"] == "What is the weather like today?"
    assert third_input["groundtruth"] is None

    # Test 5: Pull dataset and verify inputs match
    get_inputs_response = client.get(input_endpoint, headers=HEADERS_JWT)
    assert get_inputs_response.status_code == 200
    retrieved_inputs = get_inputs_response.json()
    assert len(retrieved_inputs) == 3

    # Verify the structure of retrieved inputs (with version output fields)
    for input_item in retrieved_inputs:
        assert "input_id" in input_item
        assert "input" in input_item
        assert "groundtruth" in input_item
        assert "output" in input_item
        assert "version_id" in input_item
        assert "version" in input_item
        # Initially, output and version should be None since no QA run has been performed
        assert input_item["output"] is None
        assert input_item["version_id"] is None
        assert input_item["version"] is None

    # Test 6: Update the first question
    update_input_payload = {
        "inputs_groundtruths": [
            {"id": first_input["id"], "input": "What is 2 + 2? (updated)", "groundtruth": "4 (updated)"}
        ]
    }

    update_input_response = client.patch(input_endpoint, headers=HEADERS_JWT, json=update_input_payload)
    assert update_input_response.status_code == 200
    updated_input_data = update_input_response.json()
    assert updated_input_data["inputs_groundtruths"][0]["input"] == "What is 2 + 2? (updated)"
    assert updated_input_data["inputs_groundtruths"][0]["groundtruth"] == "4 (updated)"

    # Test 7: Run QA test and validate results
    run_qa_payload = {"version_id": version_id, "input_ids": [first_input["id"], second_input["id"]]}

    # Run the QA test
    run_qa_response = client.post(
        f"/projects/{dummy_project_uuid}/qa/{dataset_id}/run", headers=HEADERS_JWT, json=run_qa_payload
    )
    assert run_qa_response.status_code == 200, f"Expected status code 200, got {run_qa_response.status_code}"

    # Validate the QA results
    qa_results = run_qa_response.json()
    assert "results" in qa_results
    assert "summary" in qa_results

    # Check that all results have input == output (dummy agent behavior)
    for result in qa_results["results"]:
        assert (
            result["input"] == result["output"]
        ), f"Input and output should be the same for dummy agent. Input: {result['input']}, Output: {result['output']}"
        assert result["success"] is True, f"All results should be successful. Result: {result}"

    # Verify summary statistics
    summary = qa_results["summary"]
    assert summary["total"] == 2
    assert summary["passed"] == 2
    assert summary["failed"] == 0
    assert summary["success_rate"] == 100.0

    # Test 8: Delete dataset and verify cleanup
    delete_dataset_payload = {"dataset_ids": [dataset_id]}

    delete_dataset_response = client.request(
        method="DELETE", url=dataset_endpoint, headers=HEADERS_JWT, json=delete_dataset_payload
    )
    assert delete_dataset_response.status_code == 200
    delete_dataset_result = delete_dataset_response.json()
    assert delete_dataset_result["message"] == "Deleted 1 datasets successfully"

    # Verify dataset is gone
    get_datasets_response = client.get(dataset_endpoint, headers=HEADERS_JWT)
    assert get_datasets_response.status_code == 200
    datasets_after_delete = get_datasets_response.json()
    assert len(datasets_after_delete) == 0

    # Verify inputs are gone (should return empty list)
    get_inputs_after_dataset_delete = client.get(input_endpoint, headers=HEADERS_JWT)
    assert get_inputs_after_dataset_delete.status_code == 200
    inputs_after_dataset_delete = get_inputs_after_dataset_delete.json()
    assert len(inputs_after_dataset_delete) == 0

    # Test 10: Create new dataset with 2 questions for pagination test
    new_dataset_payload = {"datasets": ["pagination_test_dataset"]}
    new_dataset_response = client.post(dataset_endpoint, headers=HEADERS_JWT, json=new_dataset_payload)
    assert new_dataset_response.status_code == 200
    new_dataset_id = new_dataset_response.json()["datasets"][0]["id"]

    new_input_payload = {
        "inputs_groundtruths": [
            {"input": "First question for pagination", "groundtruth": "First answer"},
            {"input": "Second question for pagination", "groundtruth": "Second answer"},
        ]
    }

    new_input_response = client.post(
        f"/projects/{dummy_project_uuid}/qa/{new_dataset_id}", headers=HEADERS_JWT, json=new_input_payload
    )
    assert new_input_response.status_code == 200

    # Test 11: Test pagination
    # Page 1 with size 1
    page1_response = client.get(
        f"/projects/{dummy_project_uuid}/qa/{new_dataset_id}?page=1&size=1", headers=HEADERS_JWT
    )
    assert page1_response.status_code == 200
    page1_data = page1_response.json()
    assert len(page1_data) == 1

    # Page 2 with size 1
    page2_response = client.get(
        f"/projects/{dummy_project_uuid}/qa/{new_dataset_id}?page=2&size=1", headers=HEADERS_JWT
    )
    assert page2_response.status_code == 200
    page2_data = page2_response.json()
    assert len(page2_data) == 1

    # Verify different questions on different pages
    assert page1_data[0]["input"] != page2_data[0]["input"]

    # Test 12: Delete project and verify complete cleanup
    delete_project_response = client.request(
        method="DELETE", url=f"/projects/{dummy_project_uuid}", headers=HEADERS_JWT
    )
    assert delete_project_response.status_code == 200

    # Verify project is gone
    get_project_response = client.get(f"/projects/{dummy_project_uuid}", headers=HEADERS_JWT)
    assert get_project_response.status_code == 404

    # Verify versions are gone (should return 404 since project doesn't exist)
    get_versions_response = client.get(versions_endpoint, headers=HEADERS_JWT)
    assert get_versions_response.status_code == 404

    # Verify datasets are gone (should return 404 since project doesn't exist)
    get_datasets_final_response = client.get(dataset_endpoint, headers=HEADERS_JWT)
    assert get_datasets_final_response.status_code == 404
