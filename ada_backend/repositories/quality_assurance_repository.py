import logging
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ada_backend.database.models import DatasetProject, InputGroundtruth, QAMetadata, VersionOutput
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
        .order_by(InputGroundtruth.position.asc())
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


def get_max_position_of_dataset(
    session: Session,
    dataset_id: UUID,
) -> Optional[int]:
    """Get the maximum position for input-groundtruth entries in a dataset.

    Returns None if no entries exist for the dataset.
    """
    max_position = (
        session.query(func.max(InputGroundtruth.position)).filter(InputGroundtruth.dataset_id == dataset_id).scalar()
    )
    return max_position


def get_positions_of_dataset(
    session: Session,
    dataset_id: UUID,
) -> List[int]:
    stmt = (
        select(InputGroundtruth.position)
        .where(InputGroundtruth.dataset_id == dataset_id)
        .order_by(InputGroundtruth.position.asc())
    )
    return session.scalars(stmt).all()


def create_inputs_groundtruths(
    session: Session,
    dataset_id: UUID,
    inputs_groundtruths_data: List[InputGroundtruthCreate],
) -> List[InputGroundtruth]:
    """Create multiple input-groundtruth entries."""
    max_position = get_max_position_of_dataset(session, dataset_id)
    starting_position = (max_position + 1) if max_position is not None else 1

    positions = [
        data.position if data.position is not None else starting_position + i
        for i, data in enumerate(inputs_groundtruths_data)
    ]

    inputs_groundtruths = [
        InputGroundtruth(
            dataset_id=dataset_id,
            input=data.input,
            groundtruth=data.groundtruth,
            position=position,
            custom_columns=data.custom_columns,
        )
        for data, position in zip(inputs_groundtruths_data, positions, strict=False)
    ]

    session.add_all(inputs_groundtruths)
    session.commit()

    for input_groundtruth in inputs_groundtruths:
        session.refresh(input_groundtruth)

    LOGGER.info(f"Created {len(inputs_groundtruths)} input-groundtruth entries for dataset {dataset_id}")
    return inputs_groundtruths


def update_inputs_groundtruths(
    session: Session,
    updates_data: List[Tuple[UUID, Optional[str], Optional[str], Optional[Dict[str, str]]]],
    dataset_id: UUID,
) -> List[InputGroundtruth]:
    """Update multiple input-groundtruth entries."""
    updated_inputs_groundtruths = []

    for input_id, input_text, groundtruth, custom_columns in updates_data:
        input_groundtruth = (
            session.query(InputGroundtruth)
            .filter(InputGroundtruth.id == input_id, InputGroundtruth.dataset_id == dataset_id)
            .first()
        )

        if input_groundtruth:
            if input_text is not None:
                input_groundtruth.input = input_text
            if groundtruth is not None:
                input_groundtruth.groundtruth = groundtruth
            if custom_columns is not None:
                current_custom_columns = input_groundtruth.custom_columns or {}
                for key, value in custom_columns.items():
                    if value is None:
                        current_custom_columns.pop(key, None)
                    else:
                        current_custom_columns[key] = value
                input_groundtruth.custom_columns = current_custom_columns if current_custom_columns else None

            updated_inputs_groundtruths.append(input_groundtruth)

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


def get_version_output_ids_by_input_ids_and_graph_runner(
    session: Session,
    input_ids: List[UUID],
    graph_runner_id: UUID,
) -> Dict[UUID, Optional[UUID]]:
    results = (
        session.query(VersionOutput.input_id, VersionOutput.id)
        .filter(
            VersionOutput.input_id.in_(input_ids),
            VersionOutput.graph_runner_id == graph_runner_id,
        )
        .all()
    )

    return {input_id: version_output_id for input_id, version_output_id in results}


def get_version_output(
    session: Session,
    version_output_id: UUID,
) -> Tuple[UUID, dict, Optional[str], str]:
    result = (
        session.query(
            VersionOutput.id,
            InputGroundtruth.input,
            InputGroundtruth.groundtruth,
            VersionOutput.output,
        )
        .join(InputGroundtruth, InputGroundtruth.id == VersionOutput.input_id)
        .filter(VersionOutput.id == version_output_id)
        .first()
    )

    return result


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


def get_dataset_existence(session: Session, project_id: UUID, dataset_id: UUID) -> bool:
    exists = session.query(
        session.query(DatasetProject)
        .filter(DatasetProject.id == dataset_id, DatasetProject.project_id == project_id)
        .exists()
    ).scalar()
    return exists


def get_qa_columns_by_dataset(session: Session, dataset_id: UUID) -> List[QAMetadata]:
    return (
        session.query(QAMetadata)
        .filter(QAMetadata.dataset_id == dataset_id)
        .order_by(QAMetadata.index_position.asc())
        .all()
    )


def get_max_position_for_metadata_column(
    session: Session,
    dataset_id: UUID,
) -> Optional[int]:
    max_position = (
        session.query(func.max(QAMetadata.index_position)).filter(QAMetadata.dataset_id == dataset_id).scalar()
    )
    return max_position


def create_qa_column(
    session: Session,
    dataset_id: UUID,
    column_id: UUID,
    column_name: str,
    index_position: int,
) -> QAMetadata:
    """Create a new QA metadata column."""
    qa_metadata = QAMetadata(
        dataset_id=dataset_id,
        column_id=column_id,
        column_name=column_name,
        index_position=index_position,
    )

    session.add(qa_metadata)
    session.commit()
    session.refresh(qa_metadata)

    LOGGER.info(
        f"Created QA column '{column_name}' (column_id: {column_id}) "
        f"at position {index_position} for dataset {dataset_id}"
    )
    return qa_metadata


def get_column_existence(session: Session, dataset_id: UUID, column_id: UUID) -> bool:
    exists = session.query(
        session.query(QAMetadata)
        .filter(QAMetadata.dataset_id == dataset_id, QAMetadata.column_id == column_id)
        .exists()
    ).scalar()
    return exists


def rename_qa_column(
    session: Session,
    dataset_id: UUID,
    column_id: UUID,
    column_name: str,
) -> QAMetadata:
    qa_metadata = (
        session.query(QAMetadata)
        .filter(QAMetadata.dataset_id == dataset_id, QAMetadata.column_id == column_id)
        .first()
    )

    qa_metadata.column_name = column_name
    session.commit()
    session.refresh(qa_metadata)

    LOGGER.info(f"Renamed QA column {column_id} to '{column_name}' for dataset {dataset_id}")
    return qa_metadata


def remove_column_content_from_custom_columns(session: Session, dataset_id: UUID, column_id: UUID) -> None:
    updated_count = session.execute(
        text(
            """
            UPDATE quality_assurance.input_groundtruth
            SET custom_columns = CASE
                WHEN (custom_columns - :column_id_str) = '{}'::jsonb THEN NULL
                ELSE custom_columns - :column_id_str
            END
            WHERE dataset_id = :dataset_id
            AND custom_columns IS NOT NULL
            AND custom_columns ? :column_id_str
            """
        ),
        {"dataset_id": str(dataset_id), "column_id_str": str(column_id)},
    ).rowcount

    session.commit()
    LOGGER.info(f"Removed column_id {column_id} from {updated_count} rows in dataset {dataset_id}")


def delete_qa_column(session: Session, dataset_id: UUID, column_id: UUID) -> None:
    (
        session.query(QAMetadata)
        .filter(QAMetadata.dataset_id == dataset_id, QAMetadata.column_id == column_id)
        .delete(synchronize_session=False)
    )

    session.commit()
    LOGGER.info(f"Deleted QA column {column_id} from dataset {dataset_id}")
