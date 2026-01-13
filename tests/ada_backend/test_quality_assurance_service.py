import csv
import io
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


def test_pagination():
    """Test pagination for GET entries endpoint with 10 rows, 5 per page."""
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"pagination_test_{project_uuid}",
        "description": "Test project for pagination",
    }
    client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)

    dataset_payload = {"datasets_name": [f"pagination_dataset_{project_uuid}"]}
    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    input_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_id}/entries"

    # Create 10 entries
    create_payload = {
        "inputs_groundtruths": [
            {"input": {"messages": [{"role": "user", "content": f"Test {i}"}]}, "groundtruth": f"GT {i}"}
            for i in range(1, 11)
        ]
    }
    create_response = client.post(input_endpoint, headers=HEADERS_JWT, json=create_payload)
    assert create_response.status_code == 200
    created = create_response.json()["inputs_groundtruths"]
    assert len(created) == 10

    # Get page 1 with 5 items per page
    page1_response = client.get(f"{input_endpoint}?page=1&page_size=5", headers=HEADERS_JWT)
    assert page1_response.status_code == 200
    page1_data = page1_response.json()
    page1_entries = page1_data["inputs_groundtruths"]
    assert len(page1_entries) == 5
    assert page1_data["pagination"]["total_items"] == 10
    assert page1_data["pagination"]["page"] == 1
    assert page1_data["pagination"]["size"] == 5

    # Verify order of page 1 (positions 1-5)
    page1_positions = [entry["position"] for entry in page1_entries]
    assert page1_positions == [1, 2, 3, 4, 5]

    # Get page 2 with 5 items per page
    page2_response = client.get(f"{input_endpoint}?page=2&page_size=5", headers=HEADERS_JWT)
    assert page2_response.status_code == 200
    page2_data = page2_response.json()
    page2_entries = page2_data["inputs_groundtruths"]
    assert len(page2_entries) == 5
    assert page2_data["pagination"]["total_items"] == 10
    assert page2_data["pagination"]["page"] == 2
    assert page2_data["pagination"]["size"] == 5

    # Verify order of page 2 (positions 6-10)
    page2_positions = [entry["position"] for entry in page2_entries]
    assert page2_positions == [6, 7, 8, 9, 10]

    # Verify no overlap between pages
    page1_ids = {entry["id"] for entry in page1_entries}
    page2_ids = {entry["id"] for entry in page2_entries}
    assert page1_ids.isdisjoint(page2_ids)

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
    input_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_id}/entries"
    create_payload = {
        "inputs_groundtruths": [
            {"input": {"messages": [{"role": "user", "content": "What is 2 + 2?"}]}, "groundtruth": "4"},
            {
                "input": {"messages": [{"role": "user", "content": "What is the capital of France?"}]},
                "groundtruth": "Paris",
            },
            {
                "input": {"messages": [{"role": "user", "content": "What is the weather like today?"}]}
            },  # No groundtruth
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
        "inputs_groundtruths": [
            {
                "id": input_to_update,
                "input": {"messages": [{"role": "user", "content": "What is 2 + 2?"}]},
                "groundtruth": "4 (updated)",
            }
        ]
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
                "name": "Start",
                "ref": "Start",
                "is_start_node": True,
                "component_id": "01357c0b-bc99-44ce-a435-995acc5e2544",  # input component UUID
                "component_version_id": "7a6e2c9b-5b1b-4a9b-9f2f-9b7f0540d4b0",
                "parameters": [
                    {
                        "value": DEFAULT_PAYLOAD_SCHEMA,
                        "name": "payload_schema",
                        "order": None,
                        "id": "1e50db7d-87cb-4c90-9082-451c4cbf93f9",
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
                "component_name": "Start",
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
                "component_version_id": "02468c0b-bc99-44ce-a435-995acc5e2545",
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
    """Test the run_qa endpoint with graph_runner_id (migrated from version field)."""

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

    # Get production graph runner ID after deployment
    project_details_response = client.get(f"/projects/{project_uuid}", headers=HEADERS_JWT)
    project_details = project_details_response.json()
    production_graph_runner = None
    for gr in project_details["graph_runners"]:
        if gr["env"] == "production":
            production_graph_runner = gr
            break
    assert production_graph_runner is not None, "Production graph runner not found"
    production_graph_runner_id = production_graph_runner["graph_runner_id"]

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
            {"input": {"messages": [{"role": "user", "content": "What is 2 + 2?"}]}, "groundtruth": "4"},
            {
                "input": {"messages": [{"role": "user", "content": "What is the capital of France?"}]},
                "groundtruth": "Paris",
            },
            {
                "input": {"messages": [{"role": "user", "content": "What is the weather like today?"}]}
            },  # No groundtruth
        ]
    }

    input_response = client.post(
        f"/projects/{project_uuid}/qa/datasets/{dataset_id}/entries", headers=HEADERS_JWT, json=input_payload
    )
    assert input_response.status_code == 200
    input_data = input_response.json()
    assert len(input_data["inputs_groundtruths"]) == 3

    # Test the run_qa endpoint with draft graph_runner_id on selected inputs
    run_qa_payload_selection = {
        "graph_runner_id": graph_runner_id,
        "input_ids": [input_data["inputs_groundtruths"][0]["id"], input_data["inputs_groundtruths"][1]["id"]],
    }

    run_qa_response_selection = client.post(
        f"/projects/{project_uuid}/qa/datasets/{dataset_id}/run", headers=HEADERS_JWT, json=run_qa_payload_selection
    )

    assert run_qa_response_selection.status_code == 200, (
        f"Expected status code 200, got {run_qa_response_selection.status_code}"
    )

    qa_results_selection = run_qa_response_selection.json()
    assert "results" in qa_results_selection
    assert "summary" in qa_results_selection

    # Check that all results have input == output (dummy agent behavior)
    for result in qa_results_selection["results"]:
        # Filter now outputs clean string content directly (not JSON)
        output_content = result["output"]
        input_content = result["input"]["messages"][0]["content"]
        assert input_content == output_content, (
            f"Input and output should be the same for dummy agent. Input: {input_content}, Output: {output_content}"
        )
        assert result["success"] is True, f"All results should be successful. Result: {result}"
        assert result["graph_runner_id"] == graph_runner_id, f"graph_runner_id should match. Result: {result}"

    # Verify summary statistics for selection
    summary_selection = qa_results_selection["summary"]
    assert summary_selection["total"] == 2
    assert summary_selection["passed"] == 2
    assert summary_selection["failed"] == 0
    assert summary_selection["success_rate"] == 100.0

    # Test the run_qa endpoint with run_all=True on production graph_runner
    run_qa_payload_all = {
        "graph_runner_id": production_graph_runner_id,
        "run_all": True,
    }

    run_qa_response_all = client.post(
        f"/projects/{project_uuid}/qa/datasets/{dataset_id}/run", headers=HEADERS_JWT, json=run_qa_payload_all
    )

    assert run_qa_response_all.status_code == 200, f"Expected status code 200, got {run_qa_response_all.status_code}"

    qa_results_all = run_qa_response_all.json()
    assert "results" in qa_results_all
    assert "summary" in qa_results_all

    # Should process all 3 entries when using run_all=True
    assert len(qa_results_all["results"]) == 3

    # Check that all results have input == output (dummy agent behavior)
    for result in qa_results_all["results"]:
        # Filter now outputs clean string content directly (not JSON)
        output_content = result["output"]
        input_content = result["input"]["messages"][0]["content"]
        assert input_content == output_content, (
            f"Input and output should be the same for dummy agent. Input: {input_content}, Output: {output_content}"
        )
        assert result["success"] is True, f"All results should be successful. Result: {result}"
        assert result["graph_runner_id"] == production_graph_runner_id, (
            f"graph_runner_id should match production. Result: {result}"
        )

    # Verify summary statistics for run_all
    summary_all = qa_results_all["summary"]
    assert summary_all["total"] == 3
    assert summary_all["passed"] == 3
    assert summary_all["failed"] == 0
    assert summary_all["success_rate"] == 100.0

    # Cleanup
    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_position_field_in_responses():
    """Test that index field is included and persists correctly after deletions."""
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"index_test_{project_uuid}",
        "description": "Test project for index field",
    }
    client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)

    dataset_payload = {"datasets_name": [f"index_dataset_{project_uuid}"]}
    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    input_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_id}/entries"

    # Add 5 entries - should get indexes 1 to 5
    create_payload = {
        "inputs_groundtruths": [
            {"input": {"messages": [{"role": "user", "content": f"Test {i}"}]}, "groundtruth": f"GT {i}"}
            for i in range(5)
        ]
    }
    create_response = client.post(input_endpoint, headers=HEADERS_JWT, json=create_payload)
    assert create_response.status_code == 200
    created = create_response.json()["inputs_groundtruths"]
    assert len(created) == 5
    positions = [entry["position"] for entry in created]
    assert positions == [1, 2, 3, 4, 5]

    # Delete entry with position 3
    entry_to_delete = next(entry["id"] for entry in created if entry["position"] == 3)
    delete_payload = {"input_groundtruth_ids": [entry_to_delete]}
    client.request(method="DELETE", url=input_endpoint, headers=HEADERS_JWT, json=delete_payload)

    # Verify remaining entries still have their original positions
    get_response = client.get(input_endpoint, headers=HEADERS_JWT)
    assert get_response.status_code == 200
    remaining = get_response.json()["inputs_groundtruths"]
    remaining_positions = [entry["position"] for entry in remaining]
    assert remaining_positions == [1, 2, 4, 5]

    # Add one new entry
    new_entry_payload = {
        "inputs_groundtruths": [
            {"input": {"messages": [{"role": "user", "content": "New entry"}]}, "groundtruth": "New GT"}
        ]
    }
    new_entry_response = client.post(input_endpoint, headers=HEADERS_JWT, json=new_entry_payload)
    assert new_entry_response.status_code == 200
    new_entry = new_entry_response.json()["inputs_groundtruths"][0]
    assert new_entry["position"] == 6

    # Verify final state
    final_response = client.get(input_endpoint, headers=HEADERS_JWT)
    final_entries = final_response.json()["inputs_groundtruths"]
    final_positions = [entry["position"] for entry in final_entries]
    assert sorted(final_positions) == [1, 2, 4, 5, 6]

    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_duplicate_positions_validation():
    """Test duplicate position validation."""
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"duplicate_test_{project_uuid}",
        "description": "Test project for duplicate positions",
    }
    client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)

    dataset_payload = {"datasets_name": [f"duplicate_dataset_{project_uuid}"]}
    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    input_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_id}/entries"
    create_payload = {
        "inputs_groundtruths": [
            {"input": {"messages": [{"role": "user", "content": "Test 1"}]}, "groundtruth": "GT 1", "position": 1},
            {"input": {"messages": [{"role": "user", "content": "Test 2"}]}, "groundtruth": "GT 2", "position": 1},
        ]
    }

    response = client.post(input_endpoint, headers=HEADERS_JWT, json=create_payload)
    assert response.status_code == 400
    assert "Duplicate positions" in response.json()["detail"]

    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_partial_position_validation():
    """Test partial position validation."""
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"partial_test_{project_uuid}",
        "description": "Test project for partial positions",
    }
    client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)

    dataset_payload = {"datasets_name": [f"partial_dataset_{project_uuid}"]}
    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    input_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_id}/entries"
    create_payload = {
        "inputs_groundtruths": [
            {"input": {"messages": [{"role": "user", "content": "Test 1"}]}, "groundtruth": "GT 1", "position": 1},
            {"input": {"messages": [{"role": "user", "content": "Test 2"}]}, "groundtruth": "GT 2"},
        ]
    }

    response = client.post(input_endpoint, headers=HEADERS_JWT, json=create_payload)
    assert response.status_code == 400
    assert "Partial positioning" in response.json()["detail"]

    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_position_auto_generation():
    """Test that positions are auto-generated when not provided."""
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"auto_index_test_{project_uuid}",
        "description": "Test project for auto-generated positions",
    }
    client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)

    dataset_payload = {"datasets_name": [f"auto_index_dataset_{project_uuid}"]}
    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    input_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_id}/entries"
    create_payload = {
        "inputs_groundtruths": [
            {"input": {"messages": [{"role": "user", "content": "Test 1"}]}, "groundtruth": "GT 1"},
            {"input": {"messages": [{"role": "user", "content": "Test 2"}]}, "groundtruth": "GT 2"},
        ]
    }

    response = client.post(input_endpoint, headers=HEADERS_JWT, json=create_payload)
    assert response.status_code == 200
    created = response.json()["inputs_groundtruths"]
    assert created[0]["position"] == 1
    assert created[1]["position"] == 2

    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_csv_import_duplicate_positions_inside_csv():
    """Test CSV import with duplicate positions within CSV."""
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"csv_duplicate_test_{project_uuid}",
        "description": "Test project for CSV duplicate positions",
    }
    client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)

    dataset_payload = {"datasets_name": [f"csv_duplicate_dataset_{project_uuid}"]}
    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    # CSV with duplicate positions
    input1 = json.dumps({"messages": [{"role": "user", "content": "Test 1"}]})
    input2 = json.dumps({"messages": [{"role": "user", "content": "Test 2"}]})
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["position", "input", "expected_output"])
    writer.writerow([1, input1, "GT 1"])
    writer.writerow([1, input2, "GT 2"])
    csv_content = csv_buffer.getvalue()
    csv_file = ("test.csv", csv_content.encode("utf-8"), "text/csv")

    import_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_id}/import"
    response = client.post(import_endpoint, headers=HEADERS_JWT, files={"file": csv_file})
    assert response.status_code == 400
    error_detail = response.json()["detail"]
    assert "Duplicate positions found in CSV import: [1]" in error_detail
    assert "CSV import" in error_detail

    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_csv_import_invalid_positions_values():
    """Test CSV import with invalid position values (non-integer)."""
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"csv_invalid_index_test_{project_uuid}",
        "description": "Test project for CSV invalid position values",
    }
    client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)

    dataset_payload = {"datasets_name": [f"csv_invalid_index_dataset_{project_uuid}"]}
    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    # CSV with invalid position value (non-integer)
    input_json = json.dumps({"messages": [{"role": "user", "content": "Test"}]})
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["position", "input", "expected_output"])
    writer.writerow(["abc", input_json, "GT"])
    csv_content = csv_buffer.getvalue()
    csv_file = ("test.csv", csv_content.encode("utf-8"), "text/csv")

    import_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_id}/import"
    response = client.post(import_endpoint, headers=HEADERS_JWT, files={"file": csv_file})
    assert response.status_code == 400
    assert "Invalid integer in 'position' column" in response.json()["detail"]
    assert "row" in response.json()["detail"]

    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)


def test_csv_import_position_less_than_one():
    """Test CSV import with position < 1."""
    project_uuid = str(uuid4())
    project_payload = {
        "project_id": project_uuid,
        "project_name": f"csv_position_lt_one_test_{project_uuid}",
        "description": "Test project for CSV position < 1",
    }
    client.post(f"/projects/{ORGANIZATION_ID}", headers=HEADERS_JWT, json=project_payload)

    dataset_payload = {"datasets_name": [f"csv_position_lt_one_dataset_{project_uuid}"]}
    dataset_response = client.post(f"/projects/{project_uuid}/qa/datasets", headers=HEADERS_JWT, json=dataset_payload)
    dataset_id = dataset_response.json()["datasets"][0]["id"]

    input_json = json.dumps({"messages": [{"role": "user", "content": "Test"}]})
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["position", "input", "expected_output"])
    writer.writerow([0, input_json, "GT"])
    csv_content = csv_buffer.getvalue()
    csv_file = ("test.csv", csv_content.encode("utf-8"), "text/csv")

    import_endpoint = f"/projects/{project_uuid}/qa/datasets/{dataset_id}/import"
    response = client.post(import_endpoint, headers=HEADERS_JWT, files={"file": csv_file})
    assert response.status_code == 400
    assert "Invalid integer in 'position' column" in response.json()["detail"]
    assert "greater than or equal to 1" in response.json()["detail"]

    client.delete(f"/projects/{project_uuid}", headers=HEADERS_JWT)
