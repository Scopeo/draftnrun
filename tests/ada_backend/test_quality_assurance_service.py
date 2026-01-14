import csv
import io
import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ada_backend.database.models import EnvType
from ada_backend.database.setup_db import get_db_session
from ada_backend.schemas.dataset_schema import DatasetCreateList, DatasetDeleteList
from ada_backend.schemas.input_groundtruth_schema import (
    InputGroundtruthCreateList,
    InputGroundtruthDeleteList,
    InputGroundtruthUpdateList,
    InputGroundtruthUpdateWithId,
    QARunRequest,
)
from ada_backend.schemas.pipeline.graph_schema import GraphUpdateSchema
from ada_backend.services.graph.deploy_graph_service import deploy_graph_service
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.services.project_service import delete_project_service, get_project_service
from ada_backend.services.qa.qa_error import (
    CSVInvalidPositionError,
    CSVNonUniquePositionError,
    QADuplicatePositionError,
    QAPartialPositionError,
)
from ada_backend.services.qa.quality_assurance_service import (
    create_datasets_service,
    create_inputs_groundtruths_service,
    delete_datasets_service,
    delete_inputs_groundtruths_service,
    get_datasets_by_project_service,
    get_inputs_groundtruths_with_version_outputs_service,
    import_qa_data_from_csv_service,
    run_qa_service,
    update_dataset_service,
    update_inputs_groundtruths_service,
)
from engine.trace.trace_context import set_trace_manager
from tests.ada_backend.test_utils import create_project_and_graph_runner

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
    """Test pagination for get_inputs_groundtruths_with_version_outputs_service with 10 rows, 5 per page."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="pagination_test", description="Test project for pagination"
        )

        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"pagination_dataset_{project_id}"])
        )
        dataset_id = dataset_data.datasets[0].id

        # Create 10 entries
        create_payload = InputGroundtruthCreateList(
            inputs_groundtruths=[
                {"input": {"messages": [{"role": "user", "content": f"Test {i}"}]}, "groundtruth": f"GT {i}"}
                for i in range(1, 11)
            ]
        )
        created_response = create_inputs_groundtruths_service(session, dataset_id, create_payload)
        created = created_response.inputs_groundtruths
        assert len(created) == 10

        # Get page 1 with 5 items per page
        page1_data = get_inputs_groundtruths_with_version_outputs_service(session, dataset_id, page=1, page_size=5)
        page1_entries = page1_data.inputs_groundtruths
        assert len(page1_entries) == 5
        assert page1_data.pagination.total_items == 10
        assert page1_data.pagination.page == 1
        assert page1_data.pagination.size == 5

        # Verify order of page 1 (positions 1-5)
        page1_positions = [entry.position for entry in page1_entries]
        assert page1_positions == [1, 2, 3, 4, 5]

        # Get page 2 with 5 items per page
        page2_data = get_inputs_groundtruths_with_version_outputs_service(session, dataset_id, page=2, page_size=5)
        page2_entries = page2_data.inputs_groundtruths
        assert len(page2_entries) == 5
        assert page2_data.pagination.total_items == 10
        assert page2_data.pagination.page == 2
        assert page2_data.pagination.size == 5

        # Verify order of page 2 (positions 6-10)
        page2_positions = [entry.position for entry in page2_entries]
        assert page2_positions == [6, 7, 8, 9, 10]

        # Verify no overlap between pages
        page1_ids = {entry.id for entry in page1_entries}
        page2_ids = {entry.id for entry in page2_entries}
        assert page1_ids.isdisjoint(page2_ids)

        delete_project_service(session=session, project_id=project_id)


def test_dataset_management():
    """Test dataset CRUD operations."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="dataset_test", description="Test project for dataset management"
        )

        # Test dataset creation
        create_payload = DatasetCreateList(datasets_name=["dataset1", "dataset2", "dataset3"])
        created_response = create_datasets_service(session, project_id, create_payload)
        created_datasets = created_response.datasets
        assert len(created_datasets) == 3

        # Test dataset retrieval
        retrieved_datasets = get_datasets_by_project_service(session, project_id)
        assert len(retrieved_datasets) == 3

        # Test dataset update
        dataset_to_update = created_datasets[0].id
        updated_dataset = update_dataset_service(session, project_id, dataset_to_update, "updated_dataset1")
        assert updated_dataset.dataset_name == "updated_dataset1"

        # Test dataset deletion
        dataset_to_delete = created_datasets[1].id
        delete_payload = DatasetDeleteList(dataset_ids=[dataset_to_delete])
        deleted_count = delete_datasets_service(session, project_id, delete_payload)
        assert deleted_count == 1  # Should have deleted 1 dataset

        # Verify the dataset was deleted
        remaining_datasets = get_datasets_by_project_service(session, project_id)
        assert len(remaining_datasets) == 2  # Should now have 2 datasets instead of 3

        delete_project_service(session=session, project_id=project_id)


def test_input_groundtruth_basic_operations():
    """Test input-groundtruth CRUD operations."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session,
            project_name_prefix="input_groundtruth_test",
            description="Test project for input-groundtruth operations",
        )

        # Create a dataset
        dataset_uuid = str(uuid4())
        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"input_groundtruth_dataset_{dataset_uuid}"])
        )
        dataset_id = dataset_data.datasets[0].id

        # Test input-groundtruth creation
        create_payload = InputGroundtruthCreateList(
            inputs_groundtruths=[
                {"input": {"messages": [{"role": "user", "content": "What is 2 + 2?"}]}, "groundtruth": "4"},
                {
                    "input": {"messages": [{"role": "user", "content": "What is the capital of France?"}]},
                    "groundtruth": "Paris",
                },
                {
                    "input": {"messages": [{"role": "user", "content": "What is the weather like today?"}]}
                },  # No groundtruth
            ]
        )
        created_response = create_inputs_groundtruths_service(session, dataset_id, create_payload)
        created_inputs = created_response.inputs_groundtruths
        assert len(created_inputs) == 3

        # Test input-groundtruth retrieval
        retrieved_data = get_inputs_groundtruths_with_version_outputs_service(session, dataset_id)
        retrieved_inputs = retrieved_data.inputs_groundtruths
        assert len(retrieved_inputs) == 3

        # Test input-groundtruth update
        input_to_update = created_inputs[0].id
        update_payload = InputGroundtruthUpdateList(
            inputs_groundtruths=[
                InputGroundtruthUpdateWithId(
                    id=input_to_update,
                    input={"messages": [{"role": "user", "content": "What is 2 + 2?"}]},
                    groundtruth="4 (updated)",
                )
            ]
        )
        updated_response = update_inputs_groundtruths_service(session, dataset_id, update_payload)
        updated_inputs = updated_response.inputs_groundtruths
        assert len(updated_inputs) == 1
        assert updated_inputs[0].groundtruth == "4 (updated)"

        # Test input-groundtruth deletion
        input_to_delete = created_inputs[1].id
        delete_payload = InputGroundtruthDeleteList(input_groundtruth_ids=[input_to_delete])
        deleted_count = delete_inputs_groundtruths_service(session, dataset_id, delete_payload)
        assert deleted_count == 1  # Should have deleted 1 input

        # Verify the input was deleted
        remaining_data = get_inputs_groundtruths_with_version_outputs_service(session, dataset_id)
        remaining_inputs = remaining_data.inputs_groundtruths
        assert len(remaining_inputs) == 2  # Should now have 2 inputs instead of 3

        delete_project_service(session=session, project_id=project_id)


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


@pytest.mark.asyncio
async def test_run_qa_service():
    """Test the run_qa_service with graph_runner_id (migrated from version field)."""
    mock_trace_manager = MagicMock()
    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=None)
    mock_trace_manager.start_span.return_value = mock_span
    mock_span.to_json.return_value = '{"context": {"trace_id": "testid"}, "attributes": {}, "parent_id": null}'
    set_trace_manager(mock_trace_manager)

    with get_db_session() as session:
        project_id, draft_graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="qa_run_test", description="Test project for QA run endpoint"
        )

        # Update the project's workflow configuration using the helper function
        workflow_config_dict = _create_dummy_agent_workflow_config()
        workflow_config = GraphUpdateSchema(**workflow_config_dict)

        # Update the graph
        await update_graph_service(session, draft_graph_runner_id, project_id, workflow_config)

        # Deploy the project to production so we can test the production version
        deploy_graph_service(session, draft_graph_runner_id, project_id)

        # Get production graph runner ID after deployment
        project_details = get_project_service(session, project_id)
        production_graph_runner = None
        for gr in project_details.graph_runners:
            if gr.env == EnvType.PRODUCTION:
                production_graph_runner = gr
                break
        assert production_graph_runner is not None, "Production graph runner not found"
        production_graph_runner_id = production_graph_runner.graph_runner_id

        # Create a dataset
        dataset_uuid = str(uuid4())
        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"qa_run_dataset_{dataset_uuid}"])
        )
        dataset_id = dataset_data.datasets[0].id

        # Create input-groundtruth entries
        input_payload = InputGroundtruthCreateList(
            inputs_groundtruths=[
                {"input": {"messages": [{"role": "user", "content": "What is 2 + 2?"}]}, "groundtruth": "4"},
                {
                    "input": {"messages": [{"role": "user", "content": "What is the capital of France?"}]},
                    "groundtruth": "Paris",
                },
                {
                    "input": {"messages": [{"role": "user", "content": "What is the weather like today?"}]}
                },  # No groundtruth
            ]
        )

        input_response = create_inputs_groundtruths_service(session, dataset_id, input_payload)
        input_data = input_response.inputs_groundtruths
        assert len(input_data) == 3

        # Test run_qa_service with draft graph_runner_id on selected inputs
        run_qa_payload_selection = QARunRequest(
            graph_runner_id=draft_graph_runner_id,
            input_ids=[input_data[0].id, input_data[1].id],
        )

        qa_results_selection = await run_qa_service(session, project_id, dataset_id, run_qa_payload_selection)

        assert "results" in qa_results_selection.model_dump()
        assert "summary" in qa_results_selection.model_dump()

        # Check that all results have input == output (dummy agent behavior)
        for result in qa_results_selection.results:
            # Filter now outputs clean string content directly (not JSON)
            output_content = result.output
            input_content = result.input["messages"][0]["content"]
            assert input_content == output_content, (
                "Input and output should be the same for dummy agent. "
                f"Input: {input_content}, Output: {output_content}"
            )
            assert result.success is True, f"All results should be successful. Result: {result}"
            assert result.graph_runner_id == draft_graph_runner_id, f"graph_runner_id should match. Result: {result}"

        # Verify summary statistics for selection
        summary_selection = qa_results_selection.summary
        assert summary_selection.total == 2
        assert summary_selection.passed == 2
        assert summary_selection.failed == 0
        assert summary_selection.success_rate == 100.0

        # Test run_qa_service with run_all=True on production graph_runner
        run_qa_payload_all = QARunRequest(
            graph_runner_id=production_graph_runner_id,
            run_all=True,
        )

        qa_results_all = await run_qa_service(session, project_id, dataset_id, run_qa_payload_all)

        assert "results" in qa_results_all.model_dump()
        assert "summary" in qa_results_all.model_dump()

        # Should process all 3 entries when using run_all=True
        assert len(qa_results_all.results) == 3

        # Check that all results have input == output (dummy agent behavior)
        for result in qa_results_all.results:
            # Filter now outputs clean string content directly (not JSON)
            output_content = result.output
            input_content = result.input["messages"][0]["content"]
            assert input_content == output_content, (
                "Input and output should be the same for dummy agent. "
                f"Input: {input_content}, Output: {output_content}"
            )
            assert result.success is True, f"All results should be successful. Result: {result}"
            assert result.graph_runner_id == production_graph_runner_id, (
                f"graph_runner_id should match production. Result: {result}"
            )

        # Verify summary statistics for run_all
        summary_all = qa_results_all.summary
        assert summary_all.total == 3
        assert summary_all.passed == 3
        assert summary_all.failed == 0
        assert summary_all.success_rate == 100.0

        delete_project_service(session=session, project_id=project_id)


def test_position_field_in_responses():
    """Test that index field is included and persists correctly after deletions."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="index_test", description="Test project for index field"
        )

        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"index_dataset_{project_id}"])
        )
        dataset_id = dataset_data.datasets[0].id

        # Add 5 entries - should get indexes 1 to 5
        create_payload = InputGroundtruthCreateList(
            inputs_groundtruths=[
                {"input": {"messages": [{"role": "user", "content": f"Test {i}"}]}, "groundtruth": f"GT {i}"}
                for i in range(5)
            ]
        )
        created_response = create_inputs_groundtruths_service(session, dataset_id, create_payload)
        created = created_response.inputs_groundtruths
        assert len(created) == 5
        positions = [entry.position for entry in created]
        assert positions == [1, 2, 3, 4, 5]

        # Delete entry with position 3
        entry_to_delete = next(entry.id for entry in created if entry.position == 3)
        delete_payload = InputGroundtruthDeleteList(input_groundtruth_ids=[entry_to_delete])
        delete_inputs_groundtruths_service(session, dataset_id, delete_payload)

        # Verify remaining entries still have their original positions
        remaining_data = get_inputs_groundtruths_with_version_outputs_service(session, dataset_id)
        remaining = remaining_data.inputs_groundtruths
        remaining_positions = [entry.position for entry in remaining]
        assert remaining_positions == [1, 2, 4, 5]

        # Add one new entry
        new_entry_payload = InputGroundtruthCreateList(
            inputs_groundtruths=[
                {"input": {"messages": [{"role": "user", "content": "New entry"}]}, "groundtruth": "New GT"}
            ]
        )
        new_entry_response = create_inputs_groundtruths_service(session, dataset_id, new_entry_payload)
        new_entry = new_entry_response.inputs_groundtruths[0]
        assert new_entry.position == 6

        # Verify final state
        final_data = get_inputs_groundtruths_with_version_outputs_service(session, dataset_id)
        final_entries = final_data.inputs_groundtruths
        final_positions = [entry.position for entry in final_entries]
        assert sorted(final_positions) == [1, 2, 4, 5, 6]

        delete_project_service(session=session, project_id=project_id)


def test_duplicate_positions_validation():
    """Test duplicate position validation."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="duplicate_test", description="Test project for duplicate positions"
        )

        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"duplicate_dataset_{project_id}"])
        )
        dataset_id = dataset_data.datasets[0].id

        create_payload = InputGroundtruthCreateList(
            inputs_groundtruths=[
                {"input": {"messages": [{"role": "user", "content": "Test 1"}]}, "groundtruth": "GT 1", "position": 1},
                {"input": {"messages": [{"role": "user", "content": "Test 2"}]}, "groundtruth": "GT 2", "position": 1},
            ]
        )

        with pytest.raises(QADuplicatePositionError) as exc_info:
            create_inputs_groundtruths_service(session, dataset_id, create_payload)
        assert "Duplicate positions" in str(exc_info.value)

        delete_project_service(session=session, project_id=project_id)


def test_partial_position_validation():
    """Test partial position validation."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="partial_test", description="Test project for partial positions"
        )

        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"partial_dataset_{project_id}"])
        )
        dataset_id = dataset_data.datasets[0].id

        create_payload = InputGroundtruthCreateList(
            inputs_groundtruths=[
                {"input": {"messages": [{"role": "user", "content": "Test 1"}]}, "groundtruth": "GT 1", "position": 1},
                {"input": {"messages": [{"role": "user", "content": "Test 2"}]}, "groundtruth": "GT 2"},
            ]
        )

        with pytest.raises(QAPartialPositionError) as exc_info:
            create_inputs_groundtruths_service(session, dataset_id, create_payload)
        assert "Partial positioning" in str(exc_info.value)

        delete_project_service(session=session, project_id=project_id)


def test_position_auto_generation():
    """Test that positions are auto-generated when not provided."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="auto_index_test", description="Test project for auto-generated positions"
        )

        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"auto_index_dataset_{project_id}"])
        )
        dataset_id = dataset_data.datasets[0].id

        create_payload = InputGroundtruthCreateList(
            inputs_groundtruths=[
                {"input": {"messages": [{"role": "user", "content": "Test 1"}]}, "groundtruth": "GT 1"},
                {"input": {"messages": [{"role": "user", "content": "Test 2"}]}, "groundtruth": "GT 2"},
            ]
        )

        created_response = create_inputs_groundtruths_service(session, dataset_id, create_payload)
        created = created_response.inputs_groundtruths
        assert created[0].position == 1
        assert created[1].position == 2

        delete_project_service(session=session, project_id=project_id)


def test_csv_import_duplicate_positions_inside_csv():
    """Test CSV import with duplicate positions within CSV."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="csv_duplicate_test", description="Test project for CSV duplicate positions"
        )

        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"csv_duplicate_dataset_{project_id}"])
        )
        dataset_id = dataset_data.datasets[0].id

        # CSV with duplicate positions
        input1 = json.dumps({"messages": [{"role": "user", "content": "Test 1"}]})
        input2 = json.dumps({"messages": [{"role": "user", "content": "Test 2"}]})
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["position", "input", "expected_output"])
        writer.writerow([1, input1, "GT 1"])
        writer.writerow([1, input2, "GT 2"])
        csv_content = csv_buffer.getvalue()
        csv_file = io.BytesIO(csv_content.encode("utf-8"))

        with pytest.raises(CSVNonUniquePositionError) as exc_info:
            import_qa_data_from_csv_service(session, dataset_id, csv_file)
        error_detail = str(exc_info.value)
        assert "Duplicate positions found in CSV import: [1]" in error_detail
        assert "CSV import" in error_detail

        delete_project_service(session=session, project_id=project_id)


def test_csv_import_invalid_positions_values():
    """Test CSV import with invalid position values (non-integer)."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session,
            project_name_prefix="csv_invalid_index_test",
            description="Test project for CSV invalid position values",
        )

        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"csv_invalid_index_dataset_{project_id}"])
        )
        dataset_id = dataset_data.datasets[0].id

        # CSV with invalid position value (non-integer)
        input_json = json.dumps({"messages": [{"role": "user", "content": "Test"}]})
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["position", "input", "expected_output"])
        writer.writerow(["abc", input_json, "GT"])
        csv_content = csv_buffer.getvalue()
        csv_file = io.BytesIO(csv_content.encode("utf-8"))

        with pytest.raises(CSVInvalidPositionError) as exc_info:
            import_qa_data_from_csv_service(session, dataset_id, csv_file)
        error_detail = str(exc_info.value)
        assert "Invalid integer in 'position' column" in error_detail
        assert "row" in error_detail

        delete_project_service(session=session, project_id=project_id)


def test_csv_import_position_less_than_one():
    """Test CSV import with position < 1."""
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(
            session, project_name_prefix="csv_position_lt_one_test", description="Test project for CSV position < 1"
        )

        dataset_data = create_datasets_service(
            session, project_id, DatasetCreateList(datasets_name=[f"csv_position_lt_one_dataset_{project_id}"])
        )
        dataset_id = dataset_data.datasets[0].id

        input_json = json.dumps({"messages": [{"role": "user", "content": "Test"}]})
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["position", "input", "expected_output"])
        writer.writerow([0, input_json, "GT"])
        csv_content = csv_buffer.getvalue()
        csv_file = io.BytesIO(csv_content.encode("utf-8"))

        with pytest.raises(CSVInvalidPositionError) as exc_info:
            import_qa_data_from_csv_service(session, dataset_id, csv_file)
        error_detail = str(exc_info.value)
        assert "Invalid integer in 'position' column" in error_detail
        assert "greater than or equal to 1" in error_detail

        delete_project_service(session=session, project_id=project_id)
