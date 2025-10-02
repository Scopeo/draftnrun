import logging
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from ada_backend.database.models import InputGroundtruth, DatasetProject, VersionOutput, EnvType
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


def get_inputs_groundtruths_with_version_outputs(
    session: Session,
    dataset_id: UUID,
    version: Optional[EnvType] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Tuple[InputGroundtruth, Optional[VersionOutput]]]:
    """
    Get input-groundtruth entries for a dataset with their version outputs.

    - If version is specified: Uses INNER JOIN to only return inputs that have outputs for that version
    - If version is None: Uses LEFT JOIN to return all inputs with their outputs (if any)

    Args:
        session: SQLAlchemy session
        dataset_id: ID of the dataset
        version: Optional version filter (draft or production)
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        List of tuples containing (InputGroundtruth, VersionOutput or None)
    """
    if version is not None:
        # Use INNER JOIN when filtering by version - only return inputs that have outputs for that version
        query = (
            session.query(InputGroundtruth, VersionOutput)
            .join(
                VersionOutput,
                and_(
                    InputGroundtruth.id == VersionOutput.input_id,
                    VersionOutput.version == version,
                ),
            )
            .filter(InputGroundtruth.dataset_id == dataset_id)
            .order_by(InputGroundtruth.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
    else:
        # Use LEFT JOIN when no version filter - return all inputs with their outputs (if any)
        query = (
            session.query(InputGroundtruth, VersionOutput)
            .outerjoin(
                VersionOutput,
                InputGroundtruth.id == VersionOutput.input_id,
            )
            .filter(InputGroundtruth.dataset_id == dataset_id)
            .order_by(InputGroundtruth.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

    return query.all()


def get_inputs_groundtruths_count_by_dataset(
    session: Session,
    dataset_id: UUID,
) -> int:
    """Get total count of input-groundtruth entries for a dataset."""
    return session.query(func.count(InputGroundtruth.id)).filter(InputGroundtruth.dataset_id == dataset_id).scalar()


def get_inputs_groundtruths_with_pagination(
    session: Session,
    dataset_id: UUID,
    page: int = 1,
    size: int = 100,
) -> tuple[List[InputGroundtruth], int]:
    """Get input-groundtruth entries with pagination and total count."""
    skip = (page - 1) * size
    inputs_groundtruths = get_inputs_groundtruths_by_dataset(session, dataset_id, skip, size)
    total_count = get_inputs_groundtruths_count_by_dataset(session, dataset_id)
    return inputs_groundtruths, total_count


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
            groundtruth=input_groundtruth_data.groundtruth,
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
    updates_data: List[Tuple[UUID, Optional[str], Optional[str]]],
    dataset_id: UUID,
) -> List[InputGroundtruth]:
    """Update multiple input-groundtruth entries."""
    updated_inputs_groundtruths = []

    for input_id, input_text, groundtruth in updates_data:
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
    version: EnvType,
) -> VersionOutput:
    """Create or update a version output entry for the given input and version.

    If a `VersionOutput` for the `(input_id, version)` pair exists, update its `output`.
    Otherwise, create a new one.
    """
    # Find existing version output for this input and version
    existing: Optional[VersionOutput] = (
        session.query(VersionOutput)
        .filter(VersionOutput.input_id == input_id, VersionOutput.version == version)
        .first()
    )

    if existing:
        existing.output = output
        session.commit()
        session.refresh(existing)
        LOGGER.info(f"Updated version output for input {input_id} and version {version}")
        return existing

    version_output = VersionOutput(
        input_id=input_id,
        output=output,
        version=version,
    )

    session.add(version_output)
    session.commit()
    session.refresh(version_output)

    LOGGER.info(f"Created version output for input {input_id} and version {version}")
    return version_output


def upsert_version_outputs(
    session: Session,
    version_outputs_data: List[Tuple[UUID, str, EnvType]],
) -> List[VersionOutput]:
    """Create or update multiple version output entries.

    For each tuple `(input_id, output, version)`, update the existing row matching
    `(input_id, version)`, or create it if missing.
    """
    results: List[VersionOutput] = []

    # Perform upserts one by one to respect existing code style and simplicity
    for input_id, output, version in version_outputs_data:
        existing: Optional[VersionOutput] = (
            session.query(VersionOutput)
            .filter(VersionOutput.input_id == input_id, VersionOutput.version == version)
            .first()
        )

        if existing:
            existing.output = output
            results.append(existing)
        else:
            results.append(
                VersionOutput(
                    input_id=input_id,
                    output=output,
                    version=version,
                )
            )

    # Separate creations from updates for a single commit
    to_create = [vo for vo in results if vo.id is None]
    if to_create:
        session.add_all(to_create)

    session.commit()

    # Refresh all objects to ensure we return persisted instances with IDs
    for vo in results:
        session.refresh(vo)

    LOGGER.info(f"Upserted {len(results)} version output entries")
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

    # Set output to empty string for all versions (draft/production) for those inputs
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
