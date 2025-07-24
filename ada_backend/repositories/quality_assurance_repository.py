import logging
from typing import List, Optional, Tuple, Union
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from ada_backend.database.models import InputGroundtruth, DatasetProject, VersionByProject, VersionOutput

LOGGER = logging.getLogger(__name__)


# Input Groundtruth functions
def get_inputs_groundtruths_by_dataset(
    session: Session,
    dataset_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[InputGroundtruth]:
    """Get all input-groundtruth entries for a dataset with pagination."""
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
    return (
        session.query(InputGroundtruth)
        .filter(InputGroundtruth.id.in_(input_ids))
        .all()
    )


def get_inputs_groundtruths_with_version_outputs(
    session: Session,
    dataset_id: UUID,
    version_id: Optional[UUID] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[Tuple[InputGroundtruth, Optional[VersionOutput]]]:
    """
    Get all input-groundtruth entries for a dataset with their version outputs using LEFT JOIN.
    
    Args:
        session: SQLAlchemy session
        dataset_id: ID of the dataset
        version_id: Optional version_id filter
        skip: Number of records to skip
        limit: Maximum number of records to return
        
    Returns:
        List of tuples containing (InputGroundtruth, VersionOutput or None)
    """
    query = (
        session.query(InputGroundtruth, VersionOutput)
        .outerjoin(
            VersionOutput,
            and_(
                InputGroundtruth.id == VersionOutput.input_id,
                VersionOutput.version_id == version_id if version_id else True
            )
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
    return (
        session.query(func.count(InputGroundtruth.id))
        .filter(InputGroundtruth.dataset_id == dataset_id)
        .scalar()
    )


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


def get_inputs_groundtruths_with_version_outputs_pagination(
    session: Session,
    dataset_id: UUID,
    version_id: Optional[UUID] = None,
    page: int = 1,
    size: int = 100,
) -> tuple[List[Tuple[InputGroundtruth, Optional[VersionOutput]]], int]:
    """Get input-groundtruth entries with version outputs using pagination and total count."""
    skip = (page - 1) * size
    results = get_inputs_groundtruths_with_version_outputs(session, dataset_id, version_id, skip, size)
    total_count = get_inputs_groundtruths_count_by_dataset(session, dataset_id)
    return results, total_count


def create_inputs_groundtruths(
    session: Session,
    dataset_id: UUID,
    inputs_groundtruths_data: List[dict],
) -> List[InputGroundtruth]:
    """Create multiple input-groundtruth entries."""
    inputs_groundtruths = []
    
    for input_groundtruth_data in inputs_groundtruths_data:
        input_groundtruth = InputGroundtruth(
            dataset_id=dataset_id,
            input=input_groundtruth_data['input'],
            groundtruth=input_groundtruth_data.get('groundtruth'),
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
            .filter(
                InputGroundtruth.id == input_id,
                InputGroundtruth.dataset_id == dataset_id
            )
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
        .filter(
            InputGroundtruth.id.in_(input_groundtruth_ids),
            InputGroundtruth.dataset_id == dataset_id
        )
        .delete(synchronize_session=False)
    )
    
    session.commit()
    
    LOGGER.info(f"Deleted {deleted_count} input-groundtruth entries for dataset {dataset_id}")
    return deleted_count


def create_version_output(
    session: Session,
    input_id: UUID,
    output: str,
    version_id: UUID,
) -> VersionOutput:
    """Create a version output entry."""
    version_output = VersionOutput(
        input_id=input_id,
        output=output,
        version_id=version_id,
    )
    
    session.add(version_output)
    session.commit()
    session.refresh(version_output)
    
    LOGGER.info(f"Created version output for input {input_id} and version {version_id}")
    return version_output


def create_version_outputs(
    session: Session,
    version_outputs_data: List[Tuple[UUID, str, UUID]],
) -> List[VersionOutput]:
    """Create multiple version output entries."""
    version_outputs = []
    
    for input_id, output, version_id in version_outputs_data:
        version_output = VersionOutput(
            input_id=input_id,
            output=output,
            version_id=version_id,
        )
        version_outputs.append(version_output)
    
    session.add_all(version_outputs)
    session.commit()
    
    # Refresh all objects to get their IDs
    for version_output in version_outputs:
        session.refresh(version_output)
    
    LOGGER.info(f"Created {len(version_outputs)} version output entries")
    return version_outputs


# Dataset functions
def get_datasets_by_project(
    session: Session,
    project_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[DatasetProject]:
    """Get all datasets for a project with pagination."""
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


def update_datasets(
    session: Session,
    updates_data: List[Tuple[UUID, Optional[str]]],
    project_id: UUID,
) -> List[DatasetProject]:
    """Update multiple datasets."""
    updated_datasets = []
    
    for dataset_id, dataset_name in updates_data:
        dataset = (
            session.query(DatasetProject)
            .filter(
                DatasetProject.id == dataset_id,
                DatasetProject.project_id == project_id
            )
            .first()
        )
        
        if dataset and dataset_name is not None:
            dataset.dataset_name = dataset_name
            updated_datasets.append(dataset)
    
    session.commit()
    
    LOGGER.info(f"Updated {len(updated_datasets)} datasets for project {project_id}")
    return updated_datasets


def delete_datasets(
    session: Session,
    dataset_ids: List[UUID],
    project_id: UUID,
) -> int:
    """Delete multiple datasets."""
    deleted_count = (
        session.query(DatasetProject)
        .filter(
            DatasetProject.id.in_(dataset_ids),
            DatasetProject.project_id == project_id
        )
        .delete(synchronize_session=False)
    )
    
    session.commit()
    
    LOGGER.info(f"Deleted {deleted_count} datasets for project {project_id}")
    return deleted_count


# Project Version functions
def get_project_versions(
    session: Session,
    project_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[VersionByProject]:
    """Get all versions for a project with pagination."""
    return (
        session.query(VersionByProject)
        .filter(VersionByProject.project_id == project_id)
        .order_by(VersionByProject.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_project_versions(
    session: Session,
    project_id: UUID,
    versions: List[str],
) -> List[VersionByProject]:
    """Create multiple project versions."""
    project_versions = []
    
    for version in versions:
        project_version = VersionByProject(
            project_id=project_id,
            version=version,
        )
        project_versions.append(project_version)
    
    session.add_all(project_versions)
    session.commit()
    
    # Refresh all objects to get their IDs
    for project_version in project_versions:
        session.refresh(project_version)
    
    LOGGER.info(f"Created {len(project_versions)} versions for project {project_id}")
    return project_versions
