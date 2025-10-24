import logging
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func

from ada_backend.database.models import InputGroundtruth, DatasetProject, VersionOutput, OutputGroundtruth
from ada_backend.schemas.input_groundtruth_schema import InputGroundtruthCreate, OutputGroundtruthCreate

LOGGER = logging.getLogger(__name__)


# Input Groundtruth functions
def get_inputs_groundtruths_by_dataset(
    session: Session,
    dataset_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[InputGroundtruth]:
    """Get input-groundtruth entries for a dataset with pagination."""
    return (
        session.query(InputGroundtruth)
        .filter(InputGroundtruth.dataset_id == dataset_id)
        .order_by(InputGroundtruth.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_inputs_groundtruths_by_ids(
    session: Session,
    input_ids: List[UUID],
) -> List[InputGroundtruth]:
    """Get input-groundtruth entries by their IDs."""
    return session.query(InputGroundtruth).filter(InputGroundtruth.id.in_(input_ids)).all()


def get_inputs_groundtruths_count_by_dataset(
    session: Session,
    dataset_id: UUID,
) -> int:
    """Get total count of input-groundtruth entries for a dataset."""
    return session.query(func.count(InputGroundtruth.id)).filter(InputGroundtruth.dataset_id == dataset_id).scalar()


def create_inputs_groundtruths(
    session: Session,
    dataset_id: UUID,
    inputs_groundtruths_data: List[InputGroundtruthCreate],
) -> List[InputGroundtruth]:
    """Create multiple input-groundtruth entries."""
    inputs_groundtruths = []

    for input_groundtruth_data in inputs_groundtruths_data:
        input_groundtruth = InputGroundtruth(
            dataset_id=dataset_id,
            input=input_groundtruth_data.input,
            conversation_id=input_groundtruth_data.conversation_id,
            role=input_groundtruth_data.role,
            order=input_groundtruth_data.order,
        )
        inputs_groundtruths.append(input_groundtruth)

    session.add_all(inputs_groundtruths)
    session.commit()

    # Refresh all objects to get their IDs
    for input_groundtruth in inputs_groundtruths:
        session.refresh(input_groundtruth)

    LOGGER.info(f"Created {len(inputs_groundtruths)} input-groundtruth entries for dataset {dataset_id}")
    return inputs_groundtruths


def update_inputs_groundtruths(
    session: Session,
    updates_data: List[Tuple[UUID, Optional[str]]],
    dataset_id: UUID,
) -> List[InputGroundtruth]:
    """Update multiple input-groundtruth entries."""
    updated_inputs_groundtruths = []

    for input_id, input_text in updates_data:
        input_groundtruth = (
            session.query(InputGroundtruth)
            .filter(InputGroundtruth.id == input_id, InputGroundtruth.dataset_id == dataset_id)
            .first()
        )

        if input_groundtruth:
            if input_text is not None:
                input_groundtruth.input = input_text

            updated_inputs_groundtruths.append(input_groundtruth)

    session.commit()

    LOGGER.info(f"Updated {len(updated_inputs_groundtruths)} input-groundtruth entries for dataset {dataset_id}")
    return updated_inputs_groundtruths


def delete_inputs_groundtruths(
    session: Session,
    input_groundtruth_ids: List[UUID],
    dataset_id: UUID,
) -> int:
    """Delete multiple input-groundtruth entries."""
    deleted_count = (
        session.query(InputGroundtruth)
        .filter(InputGroundtruth.id.in_(input_groundtruth_ids), InputGroundtruth.dataset_id == dataset_id)
        .delete(synchronize_session=False)
    )

    session.commit()

    LOGGER.info(f"Deleted {deleted_count} input-groundtruth entries for dataset {dataset_id}")
    return deleted_count


def upsert_version_output(
    session: Session,
    input_id: UUID,
    output: str,
    graph_runner_id: UUID,
) -> VersionOutput:
    """Create or update a version output entry for the given input and graph_runner_id.

    If a `VersionOutput` for the `(input_id, graph_runner_id)` pair exists, update its `output`.
    Otherwise, create a new one.
    """
    existing: Optional[VersionOutput] = (
        session.query(VersionOutput)
        .filter(VersionOutput.input_id == input_id, VersionOutput.graph_runner_id == graph_runner_id)
        .first()
    )

    if existing:
        existing.output = output
        session.commit()
        session.refresh(existing)
        LOGGER.info(f"Updated version output for input {input_id} and graph_runner_id {graph_runner_id}")
        return existing

    version_output = VersionOutput(
        input_id=input_id,
        output=output,
        graph_runner_id=graph_runner_id,
    )

    session.add(version_output)
    session.commit()
    session.refresh(version_output)

    LOGGER.info(f"Created version output for input {input_id} and graph_runner_id {graph_runner_id}")
    return version_output


def get_outputs_by_graph_runner(
    session: Session,
    dataset_id: UUID,
    graph_runner_id: UUID,
) -> List[Tuple[UUID, str]]:
    """Get outputs for a specific graph_runner.

    Args:
        session: SQLAlchemy session
        dataset_id: ID of the dataset
        graph_runner_id: ID of the graph runner

    Returns:
        List of tuples (input_id, output)
    """
    results = (
        session.query(VersionOutput.input_id, VersionOutput.output)
        .join(InputGroundtruth, InputGroundtruth.id == VersionOutput.input_id)
        .filter(InputGroundtruth.dataset_id == dataset_id, VersionOutput.graph_runner_id == graph_runner_id)
        .all()
    )

    return results


def clear_version_outputs_for_input_ids(
    session: Session,
    input_ids: List[UUID],
) -> int:
    """Set output to empty string for all version outputs linked to given inputs.

    Args:
        session: SQLAlchemy session
        input_ids: List of input IDs whose version outputs should be cleared

    Returns:
        Number of version output rows affected
    """
    if not input_ids:
        return 0

    updated_count = (
        session.query(VersionOutput)
        .filter(VersionOutput.input_id.in_(input_ids))
        .update({VersionOutput.output: ""}, synchronize_session=False)
    )

    session.commit()
    LOGGER.info(f"Cleared outputs for {updated_count} version output rows (inputs: {len(input_ids)})")
    return updated_count


# Dataset functions
def get_datasets_by_project(
    session: Session,
    project_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[DatasetProject]:
    """Get datasets for a project with pagination."""
    return (
        session.query(DatasetProject)
        .filter(DatasetProject.project_id == project_id)
        .order_by(DatasetProject.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_datasets(
    session: Session,
    project_id: UUID,
    dataset_names: List[str],
) -> List[DatasetProject]:
    """Create multiple datasets."""
    datasets = []

    for dataset_name in dataset_names:
        dataset = DatasetProject(
            project_id=project_id,
            dataset_name=dataset_name,
        )
        datasets.append(dataset)

    session.add_all(datasets)
    session.commit()

    # Refresh all objects to get their IDs
    for dataset in datasets:
        session.refresh(dataset)

    LOGGER.info(f"Created {len(datasets)} datasets for project {project_id}")
    return datasets


def update_dataset(
    session: Session,
    dataset_id: UUID,
    dataset_name: Optional[str],
    project_id: UUID,
) -> DatasetProject:
    """Update a dataset"""
    dataset = (
        session.query(DatasetProject)
        .filter(DatasetProject.id == dataset_id, DatasetProject.project_id == project_id)
        .first()
    )

    if not dataset:
        raise ValueError(f"Dataset {dataset_id} not found in project {project_id}")

    if dataset_name is not None:
        dataset.dataset_name = dataset_name

    session.commit()

    LOGGER.info(f"Updated dataset {dataset_id} with name '{dataset_name}' for project {project_id}")
    return dataset


def delete_datasets(
    session: Session,
    dataset_ids: List[UUID],
    project_id: UUID,
) -> int:
    """Delete multiple datasets."""
    deleted_count = (
        session.query(DatasetProject)
        .filter(DatasetProject.id.in_(dataset_ids), DatasetProject.project_id == project_id)
        .delete(synchronize_session=False)
    )

    session.commit()

    LOGGER.info(f"Deleted {deleted_count} datasets for project {project_id}")
    return deleted_count


# Output Groundtruth functions
def create_output_groundtruths(
    session: Session,
    outputs_data: List[OutputGroundtruthCreate],
) -> List[OutputGroundtruth]:
    """Create multiple output groundtruth entries."""
    outputs = []

    for output_data in outputs_data:
        output_entry = OutputGroundtruth(
            message=output_data.message,
            message_id=output_data.message_id,
        )
        outputs.append(output_entry)

    session.add_all(outputs)
    session.commit()

    # Refresh all objects to get their IDs
    for output_entry in outputs:
        session.refresh(output_entry)

    LOGGER.info(f"Created {len(outputs)} output groundtruth entries")
    return outputs


def get_outputs_by_conversation(
    session: Session,
    conversation_id: str,
) -> List[Tuple[InputGroundtruth, OutputGroundtruth]]:
    """Get all output groundtruth entries for a conversation."""
    return (
        session.query(InputGroundtruth, OutputGroundtruth)
        .join(OutputGroundtruth, InputGroundtruth.id == OutputGroundtruth.message_id)
        .filter(InputGroundtruth.conversation_id == conversation_id)
        .order_by(InputGroundtruth.order)
        .all()
    )
