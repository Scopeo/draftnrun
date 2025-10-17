"""
Pytest tests for Quality Assurance Repository functions.

Tests cover the migration from EnvType-based version system to graph_runner_id-based system.
Specifically tests:
1. upsert_version_output (create and update)
2. get_outputs_by_graph_runner
3. clear_version_outputs_for_input_ids
"""

import pytest
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ada_backend.database.models import (
    VersionOutput,
    InputGroundtruth,
    DatasetProject,
    WorkflowProject,
    GraphRunner,
    ProjectType,
)
from ada_backend.repositories.quality_assurance_repository import (
    upsert_version_output,
    get_outputs_by_graph_runner,
    get_inputs_groundtruths_by_dataset,
    clear_version_outputs_for_input_ids,
)


class TestUpsertVersionOutput:
    """Test upsert_version_output function."""

    def test_create_new_output(self, ada_backend_mock_session: Session):
        """Test creating a new version output."""
        session = ada_backend_mock_session

        project = WorkflowProject(
            id=uuid4(),
            name="Test Project",
            description="Test",
            type=ProjectType.WORKFLOW,
            organization_id=uuid4(),
        )
        session.add(project)

        graph_runner = GraphRunner(id=uuid4())
        session.add(graph_runner)

        dataset = DatasetProject(id=uuid4(), project_id=project.id, dataset_name="Test Dataset")
        session.add(dataset)

        input_groundtruth = InputGroundtruth(
            id=uuid4(),
            dataset_id=dataset.id,
            input="Test input",
            groundtruth="Test groundtruth",
        )
        session.add(input_groundtruth)
        session.commit()

        result = upsert_version_output(
            session=session,
            input_id=input_groundtruth.id,
            output="Test output",
            graph_runner_id=graph_runner.id,
        )

        assert result is not None
        assert result.input_id == input_groundtruth.id
        assert result.output == "Test output"
        assert result.graph_runner_id == graph_runner.id

    def test_update_existing_output(self, ada_backend_mock_session: Session):
        """Test updating an existing version output maintains same ID."""
        session = ada_backend_mock_session

        project = WorkflowProject(
            id=uuid4(),
            name="Test Project",
            description="Test",
            type=ProjectType.WORKFLOW,
            organization_id=uuid4(),
        )
        session.add(project)

        graph_runner = GraphRunner(id=uuid4())
        session.add(graph_runner)

        dataset = DatasetProject(id=uuid4(), project_id=project.id, dataset_name="Test Dataset")
        session.add(dataset)

        input_groundtruth = InputGroundtruth(
            id=uuid4(),
            dataset_id=dataset.id,
            input="Test input",
            groundtruth="Test groundtruth",
        )
        session.add(input_groundtruth)
        session.commit()

        result1 = upsert_version_output(
            session=session,
            input_id=input_groundtruth.id,
            output="Original output",
            graph_runner_id=graph_runner.id,
        )
        original_id = result1.id

        result2 = upsert_version_output(
            session=session,
            input_id=input_groundtruth.id,
            output="Updated output",
            graph_runner_id=graph_runner.id,
        )

        assert result2.id == original_id
        assert result2.output == "Updated output"

        all_outputs = (
            session.query(VersionOutput)
            .filter(
                VersionOutput.input_id == input_groundtruth.id,
                VersionOutput.graph_runner_id == graph_runner.id,
            )
            .all()
        )
        assert len(all_outputs) == 1

    def test_unique_constraint_enforced(self, ada_backend_mock_session: Session):
        """Test that unique constraint prevents duplicate (input_id, graph_runner_id)."""
        session = ada_backend_mock_session

        project = WorkflowProject(
            id=uuid4(),
            name="Test Project",
            description="Test",
            type=ProjectType.WORKFLOW,
            organization_id=uuid4(),
        )
        session.add(project)

        graph_runner = GraphRunner(id=uuid4())
        session.add(graph_runner)

        dataset = DatasetProject(id=uuid4(), project_id=project.id, dataset_name="Test Dataset")
        session.add(dataset)

        input_groundtruth = InputGroundtruth(
            id=uuid4(),
            dataset_id=dataset.id,
            input="Test input",
            groundtruth="Test groundtruth",
        )
        session.add(input_groundtruth)
        session.commit()

        version_output_1 = VersionOutput(
            id=uuid4(),
            input_id=input_groundtruth.id,
            output="Test output 1",
            graph_runner_id=graph_runner.id,
        )
        session.add(version_output_1)
        session.commit()

        version_output_2 = VersionOutput(
            id=uuid4(),
            input_id=input_groundtruth.id,
            output="Test output 2",
            graph_runner_id=graph_runner.id,
        )
        session.add(version_output_2)

        with pytest.raises(IntegrityError):
            session.commit()


class TestGetOutputsByGraphRunner:
    """Test get_outputs_by_graph_runner function."""

    def test_get_outputs_for_specific_graph_runner(self, ada_backend_mock_session: Session):
        """Test retrieving outputs only for specified graph_runner."""
        session = ada_backend_mock_session

        project = WorkflowProject(
            id=uuid4(),
            name="Test Project",
            description="Test",
            type=ProjectType.WORKFLOW,
            organization_id=uuid4(),
        )
        session.add(project)

        graph_runner_1 = GraphRunner(id=uuid4())
        graph_runner_2 = GraphRunner(id=uuid4())
        session.add_all([graph_runner_1, graph_runner_2])

        dataset = DatasetProject(id=uuid4(), project_id=project.id, dataset_name="Test Dataset")
        session.add(dataset)

        inputs = [
            InputGroundtruth(id=uuid4(), dataset_id=dataset.id, input=f"Input {i}", groundtruth=f"GT {i}")
            for i in range(3)
        ]
        session.add_all(inputs)
        session.commit()

        for i, inp in enumerate(inputs[:2]):
            version_output = VersionOutput(
                id=uuid4(),
                input_id=inp.id,
                output=f"GR1 Output {i}",
                graph_runner_id=graph_runner_1.id,
            )
            session.add(version_output)

        version_output = VersionOutput(
            id=uuid4(),
            input_id=inputs[2].id,
            output="GR2 Output 2",
            graph_runner_id=graph_runner_2.id,
        )
        session.add(version_output)
        session.commit()

        results = get_outputs_by_graph_runner(
            session=session,
            dataset_id=dataset.id,
            graph_runner_id=graph_runner_1.id,
        )

        assert len(results) == 2
        input_ids = [r[0] for r in results]
        assert inputs[0].id in input_ids
        assert inputs[1].id in input_ids

    def test_returns_empty_when_no_outputs(self, ada_backend_mock_session: Session):
        """Test returns empty list when no outputs exist."""
        session = ada_backend_mock_session

        project = WorkflowProject(
            id=uuid4(),
            name="Test Project",
            description="Test",
            type=ProjectType.WORKFLOW,
            organization_id=uuid4(),
        )
        session.add(project)

        graph_runner = GraphRunner(id=uuid4())
        session.add(graph_runner)

        dataset = DatasetProject(id=uuid4(), project_id=project.id, dataset_name="Test Dataset")
        session.add(dataset)
        session.commit()

        results = get_outputs_by_graph_runner(
            session=session,
            dataset_id=dataset.id,
            graph_runner_id=graph_runner.id,
        )

        assert len(results) == 0

    def test_nonexistent_ids_return_empty(self, ada_backend_mock_session: Session):
        """Test with nonexistent dataset_id and graph_runner_id returns empty."""
        session = ada_backend_mock_session

        results = get_outputs_by_graph_runner(
            session=session,
            dataset_id=uuid4(),
            graph_runner_id=uuid4(),
        )

        assert results == []


class TestGetInputsGroundtruthsByDataset:
    """Test get_inputs_groundtruths_by_dataset function (after migration)."""

    def test_returns_inputs_without_outputs(self, ada_backend_mock_session: Session):
        """Test function returns all inputs (outputs retrieved separately now)."""
        session = ada_backend_mock_session

        project = WorkflowProject(
            id=uuid4(),
            name="Test Project",
            description="Test",
            type=ProjectType.WORKFLOW,
            organization_id=uuid4(),
        )
        session.add(project)

        dataset = DatasetProject(id=uuid4(), project_id=project.id, dataset_name="Test Dataset")
        session.add(dataset)

        inputs = [
            InputGroundtruth(id=uuid4(), dataset_id=dataset.id, input=f"Input {i}", groundtruth=f"GT {i}")
            for i in range(3)
        ]
        session.add_all(inputs)
        session.commit()

        results = get_inputs_groundtruths_by_dataset(
            session=session,
            dataset_id=dataset.id,
        )

        assert len(results) == 3
        for input_gt in results:
            assert input_gt is not None
            assert isinstance(input_gt, InputGroundtruth)

    def test_returns_empty_for_nonexistent_dataset(self, ada_backend_mock_session: Session):
        """Test returns empty list for nonexistent dataset."""
        session = ada_backend_mock_session

        results = get_inputs_groundtruths_by_dataset(
            session=session,
            dataset_id=uuid4(),
        )

        assert len(results) == 0


class TestClearVersionOutputs:
    """Test clear_version_outputs_for_input_ids function."""

    def test_clears_specified_inputs(self, ada_backend_mock_session: Session):
        """Test clearing version outputs for specific input IDs (sets output to empty string)."""
        session = ada_backend_mock_session

        project = WorkflowProject(
            id=uuid4(),
            name="Test Project",
            description="Test",
            type=ProjectType.WORKFLOW,
            organization_id=uuid4(),
        )
        session.add(project)

        graph_runner = GraphRunner(id=uuid4())
        session.add(graph_runner)

        dataset = DatasetProject(id=uuid4(), project_id=project.id, dataset_name="Test Dataset")
        session.add(dataset)

        inputs = [
            InputGroundtruth(id=uuid4(), dataset_id=dataset.id, input=f"Input {i}", groundtruth=f"GT {i}")
            for i in range(3)
        ]
        session.add_all(inputs)
        session.commit()

        for inp in inputs:
            version_output = VersionOutput(
                id=uuid4(),
                input_id=inp.id,
                output=f"Output for {inp.input}",
                graph_runner_id=graph_runner.id,
            )
            session.add(version_output)
        session.commit()

        clear_version_outputs_for_input_ids(
            session=session,
            input_ids=[inputs[0].id, inputs[1].id],
        )

        all_outputs = session.query(VersionOutput).filter(VersionOutput.graph_runner_id == graph_runner.id).all()
        assert len(all_outputs) == 3

        cleared_outputs = [vo for vo in all_outputs if vo.input_id in [inputs[0].id, inputs[1].id]]
        assert len(cleared_outputs) == 2
        assert all(vo.output == "" for vo in cleared_outputs)

        uncleared_output = [vo for vo in all_outputs if vo.input_id == inputs[2].id][0]
        assert uncleared_output.output == "Output for Input 2"

    def test_empty_list_does_nothing(self, ada_backend_mock_session: Session):
        """Test clearing with empty list doesn't affect data."""
        session = ada_backend_mock_session

        project = WorkflowProject(
            id=uuid4(),
            name="Test Project",
            description="Test",
            type=ProjectType.WORKFLOW,
            organization_id=uuid4(),
        )
        session.add(project)

        graph_runner = GraphRunner(id=uuid4())
        session.add(graph_runner)

        dataset = DatasetProject(id=uuid4(), project_id=project.id, dataset_name="Test Dataset")
        session.add(dataset)

        input_groundtruth = InputGroundtruth(
            id=uuid4(),
            dataset_id=dataset.id,
            input="Test input",
            groundtruth="Test groundtruth",
        )
        session.add(input_groundtruth)
        session.commit()

        version_output = VersionOutput(
            id=uuid4(),
            input_id=input_groundtruth.id,
            output="Test output",
            graph_runner_id=graph_runner.id,
        )
        session.add(version_output)
        session.commit()

        clear_version_outputs_for_input_ids(session=session, input_ids=[])

        remaining = session.query(VersionOutput).filter(VersionOutput.graph_runner_id == graph_runner.id).all()
        assert len(remaining) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
