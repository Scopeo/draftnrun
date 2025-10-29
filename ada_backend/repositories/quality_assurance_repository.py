import logging
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func

from ada_backend.database.models import InputGroundtruth, DatasetProject, VersionOutput, OutputGroundtruth, RoleType
from ada_backend.schemas.input_groundtruth_schema import InputGroundtruthCreate

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


def get_inputs_by_dataset_and_conversation_ids(
    session: Session,
    dataset_id: UUID,
    conversation_ids: List[UUID],
) -> List[InputGroundtruth]:
    """Get input-groundtruth entries for given dataset filtered by conversation ids.

    Results are ordered by conversation then message order to help reconstruct conversations.
    """
    if not conversation_ids:
        return []

    return (
        session.query(InputGroundtruth)
        .filter(InputGroundtruth.dataset_id == dataset_id)
        .filter(InputGroundtruth.conversation_id.in_(conversation_ids))
        .order_by(InputGroundtruth.conversation_id, InputGroundtruth.order.asc())
        .all()
    )


def get_conversations_with_outputs(
    session: Session,
    dataset_id: UUID,
    skip: int = 0,
    limit: Optional[int] = None,
) -> List[Tuple[List[InputGroundtruth], Optional[OutputGroundtruth]]]:
    """Get conversations with their inputs and corresponding output groundtruths.

    For each conversation:
    - Returns all inputs ordered by message order
    - Returns the output groundtruth linked to the last input (highest order) in the conversation

    Args:
        session: SQLAlchemy session
        dataset_id: ID of the dataset
        skip: Number of conversations to skip (for pagination)
        limit: Maximum number of conversations to return (None = all)

    Returns:
        List of tuples: (list of inputs, output_groundtruth or None)
    """
    # Get all distinct conversation IDs with pagination
    conversation_ids_query = (
        session.query(InputGroundtruth.conversation_id)
        .filter(InputGroundtruth.dataset_id == dataset_id)
        .group_by(InputGroundtruth.conversation_id)
        .order_by(func.max(InputGroundtruth.created_at).desc())
        .offset(skip)
    )

    if limit is not None:
        conversation_ids_query = conversation_ids_query.limit(limit)

    conversation_ids = [row[0] for row in conversation_ids_query.all()]

    if not conversation_ids:
        return []

    # Get all inputs for these conversations
    all_inputs = (
        session.query(InputGroundtruth)
        .filter(InputGroundtruth.dataset_id == dataset_id, InputGroundtruth.conversation_id.in_(conversation_ids))
        .order_by(InputGroundtruth.conversation_id, InputGroundtruth.order.asc())
        .all()
    )

    # Group inputs by conversation_id and track the maximum order
    conversations_map = {}
    last_input_ids = {}
    max_orders = {}  # Track the maximum order for each conversation

    for input_item in all_inputs:
        conv_id = input_item.conversation_id
        if conv_id not in conversations_map:
            conversations_map[conv_id] = []
        conversations_map[conv_id].append(input_item)

        # Track the last input (highest order) for each conversation
        if conv_id not in max_orders or input_item.order > max_orders[conv_id]:
            max_orders[conv_id] = input_item.order
            last_input_ids[conv_id] = input_item.id

    # Get output groundtruths for the last inputs
    output_groundtruths = {}
    if last_input_ids:
        outputs = (
            session.query(OutputGroundtruth).filter(OutputGroundtruth.message_id.in_(last_input_ids.values())).all()
        )

        # Map outputs by message_id
        output_by_message_id = {output.message_id: output for output in outputs}

        # Map outputs to conversations
        for conv_id, last_input_id in last_input_ids.items():
            if last_input_id in output_by_message_id:
                output_groundtruths[conv_id] = output_by_message_id[last_input_id]

    # Build result list maintaining the original order
    result = []
    for conv_id in conversation_ids:
        inputs = conversations_map.get(conv_id, [])
        output = output_groundtruths.get(conv_id)
        result.append((inputs, output))

    return result


def get_inputs_groundtruths_count_by_dataset(
    session: Session,
    dataset_id: UUID,
) -> int:
    """Get total count of input-groundtruth entries for a dataset."""
    return session.query(func.count(InputGroundtruth.id)).filter(InputGroundtruth.dataset_id == dataset_id).scalar()


def get_conversations_count_by_dataset(
    session: Session,
    dataset_id: UUID,
) -> int:
    """Get total count of unique conversations for a dataset."""
    return (
        session.query(func.count(func.distinct(InputGroundtruth.conversation_id)))
        .filter(InputGroundtruth.dataset_id == dataset_id)
        .scalar()
    )


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
    dataset_id: UUID,
    input_id: UUID,
    input_text: Optional[str] = None,
    role: Optional[RoleType] = None,
    order: Optional[int] = None,
) -> List[InputGroundtruth]:
    """Update multiple input-groundtruth entries.

    Args:
        session: SQLAlchemy session
        dataset_id: Dataset ID
        input_id: Input ID
        input_text: Optional input text
        role: Optional role
        order: Optional order

    Returns:
        List of updated InputGroundtruth objects
    """
    updated_inputs_groundtruths = []
    input_groundtruth = (
        session.query(InputGroundtruth)
        .filter(InputGroundtruth.id == input_id, InputGroundtruth.dataset_id == dataset_id)
        .first()
    )

    if input_groundtruth:
        if input_text is not None:
            input_groundtruth.input = input_text
        if role is not None:
            input_groundtruth.role = role
        if order is not None:
            input_groundtruth.order = order

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


def create_output_groundtruths(
    session: Session,
    message: str,
    message_id: UUID,
) -> OutputGroundtruth:
    """Create an output-groundtruth entry linked to an input message."""
    output_groundtruth = OutputGroundtruth(
        message=message,
        message_id=message_id,
    )

    session.add(output_groundtruth)
    session.commit()

    session.refresh(output_groundtruth)

    LOGGER.info(f"Created output-groundtruth entry for message {message_id}")
    return output_groundtruth


def get_output_groundtruths_by_message_id(
    session: Session,
    message_id: UUID,
) -> List[OutputGroundtruth]:
    """Get the most recent output-groundtruth entry by message ID (or None)."""
    return (
        session.query(OutputGroundtruth)
        .filter(OutputGroundtruth.message_id == message_id)
        .order_by(OutputGroundtruth.created_at.desc())
        .all()
    )


def update_output_groundtruth(
    session: Session,
    output_id: Optional[UUID],
    message_id: Optional[UUID],
    output_message: Optional[str],
) -> OutputGroundtruth:
    """Update an output groundtruth for a given id, or create a new one if it doesn't exist.

    Args:
        session: SQLAlchemy session
        output_id: The output_groundtruth ID (if updating existing)
        message_id: The message_id (InputGroundtruth.id) for creating new or verifying
        output_message: The output message text

    Returns:
        The updated or created OutputGroundtruth
    """
    # First, try to find by output_id (primary key)
    existing = None
    if output_id:
        existing = session.query(OutputGroundtruth).filter(OutputGroundtruth.id == output_id).first()

    # If not found by output_id, check if there's an existing one for this message_id
    if not existing and message_id:
        existing = session.query(OutputGroundtruth).filter(OutputGroundtruth.message_id == message_id).first()

    # If still not found, create a new one
    if not existing:
        if not message_id:
            raise ValueError("Cannot create output groundtruth: message_id is required when output_id does not exist")
        if not output_message:
            raise ValueError("Cannot create output groundtruth: output_message is required")

        existing = OutputGroundtruth(
            message=output_message,
            message_id=message_id,
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)
        LOGGER.info(f"Created output-groundtruth for message_id {message_id}")
        return existing

    # Update existing output groundtruth
    # Only update the message, not the message_id (relationship should not change)
    if output_message is not None:
        existing.message = output_message
    session.commit()
    session.refresh(existing)
    LOGGER.info(f"Updated output-groundtruth with id {existing.id}")
    return existing


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
