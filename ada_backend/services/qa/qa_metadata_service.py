import logging
import uuid
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.quality_assurance_repository import (
    check_column_exist,
    check_dataset_belongs_to_project,
    create_custom_column,
    delete_custom_column,
    get_dataset_custom_columns_display_max_position,
    get_qa_columns_by_dataset,
    remove_column_value_from_custom_column,
    rename_custom_column,
)
from ada_backend.schemas.qa_metadata_schema import QAColumnResponse
from ada_backend.services.qa.qa_error import QAColumnNotFoundError, QADatasetNotInProjectError

LOGGER = logging.getLogger(__name__)


def get_qa_columns_by_dataset_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
) -> List[QAColumnResponse]:
    try:
        dataset_existence = check_dataset_belongs_to_project(session, project_id, dataset_id)
        if not dataset_existence:
            raise QADatasetNotInProjectError(project_id, dataset_id)

        columns = get_qa_columns_by_dataset(session, dataset_id)

        return [QAColumnResponse.model_validate(col) for col in columns]
    except QADatasetNotInProjectError:
        raise


def create_qa_column_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    column_name: str,
) -> QAColumnResponse:
    try:
        dataset_existence = check_dataset_belongs_to_project(session, project_id, dataset_id)
        if not dataset_existence:
            raise QADatasetNotInProjectError(project_id, dataset_id)

        max_position = get_dataset_custom_columns_display_max_position(session, dataset_id)
        new_position = (max_position + 1) if max_position is not None else 0

        column_id = uuid.uuid4()

        qa_metadata = create_custom_column(
            session=session,
            dataset_id=dataset_id,
            column_id=column_id,
            column_name=column_name,
            column_position=new_position,
        )

        return QAColumnResponse.model_validate(qa_metadata)
    except QADatasetNotInProjectError:
        LOGGER.error(f"Dataset {dataset_id} not found in project {project_id}")
        raise


def rename_qa_column_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    column_id: UUID,
    column_name: str,
) -> QAColumnResponse:
    try:
        dataset_existence = check_dataset_belongs_to_project(session, project_id, dataset_id)
        if not dataset_existence:
            raise QADatasetNotInProjectError(project_id, dataset_id)

        column_existence = check_column_exist(session, dataset_id, column_id)
        if not column_existence:
            raise QAColumnNotFoundError(dataset_id, column_id)

        qa_metadata = rename_custom_column(
            session=session,
            dataset_id=dataset_id,
            column_id=column_id,
            column_name=column_name,
        )

        LOGGER.info(
            f"Renamed QA column {column_id} to '{column_name}' for dataset {dataset_id} in project {project_id}"
        )

        return QAColumnResponse.model_validate(qa_metadata)
    except (QADatasetNotInProjectError, QAColumnNotFoundError):
        raise


def delete_qa_column_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    column_id: UUID,
) -> dict:
    try:
        dataset_existence = check_dataset_belongs_to_project(session, project_id, dataset_id)
        if not dataset_existence:
            raise QADatasetNotInProjectError(project_id, dataset_id)

        column_existence = check_column_exist(session, dataset_id, column_id)
        if not column_existence:
            raise QAColumnNotFoundError(dataset_id, column_id)

        remove_column_value_from_custom_column(session, dataset_id, column_id)
        delete_custom_column(session, dataset_id, column_id)

        LOGGER.info(f"Deleted QA column {column_id} from dataset {dataset_id} in project {project_id}")

        return {"message": f"Deleted column {column_id} successfully"}
    except (QADatasetNotInProjectError, QAColumnNotFoundError):
        raise
