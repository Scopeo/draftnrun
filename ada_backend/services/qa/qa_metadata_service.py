import logging
import uuid
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.quality_assurance_repository import (
    create_qa_column,
    delete_qa_column,
    get_column_existence,
    get_dataset_existence,
    get_max_position_for_metadata_column,
    get_qa_columns_by_dataset,
    remove_column_content_from_custom_columns,
    rename_qa_column,
)
from ada_backend.schemas.qa_metadata_schema import QAColumnListResponse, QAColumnResponse
from ada_backend.services.qa.qa_error import (
    QAColumnNotFoundError,
    QADatasetCreateCustomColumnError,
    QADatasetDeleteCustomColumnError,
    QADatasetGetCustomColumnsError,
    QADatasetNotInProjectError,
    QADatasetRenameCustomColumnError,
)

LOGGER = logging.getLogger(__name__)


def get_qa_columns_by_dataset_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
) -> QAColumnListResponse:
    try:
        dataset_existence = get_dataset_existence(session, project_id, dataset_id)
        if not dataset_existence:
            raise QADatasetNotInProjectError(project_id, dataset_id)

        columns = get_qa_columns_by_dataset(session, dataset_id)

        return QAColumnListResponse(columns=[QAColumnResponse.model_validate(col) for col in columns])
    except QADatasetNotInProjectError:
        raise
    except Exception as e:
        LOGGER.error(f"Error in get_qa_columns_by_dataset_service: {str(e)}")
        raise QADatasetGetCustomColumnsError(project_id, dataset_id, str(e)) from e


def create_qa_column_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    column_name: str,
) -> QAColumnResponse:
    try:
        dataset_existence = get_dataset_existence(session, project_id, dataset_id)
        if not dataset_existence:
            raise QADatasetNotInProjectError(project_id, dataset_id)

        max_position = get_max_position_for_metadata_column(session, dataset_id)
        new_position = (max_position + 1) if max_position is not None else 0

        column_id = uuid.uuid4()

        qa_metadata = create_qa_column(
            session=session,
            dataset_id=dataset_id,
            column_id=column_id,
            column_name=column_name,
            index_position=new_position,
        )

        LOGGER.info(
            f"Created QA column '{column_name}' (column_id: {column_id}) at position {new_position} "
            f"for dataset {dataset_id} in project {project_id}"
        )

        return QAColumnResponse.model_validate(qa_metadata)
    except QADatasetNotInProjectError:
        LOGGER.error(f"Dataset {dataset_id} not found in project {project_id}")
        raise
    except Exception as e:
        LOGGER.error(f"Error in create_qa_column_service: {str(e)}")
        raise QADatasetCreateCustomColumnError(dataset_id, project_id, column_name, str(e)) from e


def rename_qa_column_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    column_id: UUID,
    column_name: str,
) -> QAColumnResponse:
    try:
        dataset_existence = get_dataset_existence(session, project_id, dataset_id)
        if not dataset_existence:
            raise QADatasetNotInProjectError(project_id, dataset_id)

        column_existence = get_column_existence(session, dataset_id, column_id)
        if not column_existence:
            raise QAColumnNotFoundError(dataset_id, column_id)

        qa_metadata = rename_qa_column(
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
    except Exception as e:
        LOGGER.error(f"Error in rename_qa_column_service: {str(e)}")
        raise QADatasetRenameCustomColumnError(project_id, dataset_id, column_id, column_name, str(e)) from e


def delete_qa_column_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    column_id: UUID,
) -> dict:
    try:
        dataset_existence = get_dataset_existence(session, project_id, dataset_id)
        if not dataset_existence:
            raise QADatasetNotInProjectError(project_id, dataset_id)

        column_existence = get_column_existence(session, dataset_id, column_id)
        if not column_existence:
            raise QAColumnNotFoundError(dataset_id, column_id)

        remove_column_content_from_custom_columns(session, dataset_id, column_id)
        delete_qa_column(session, dataset_id, column_id)

        LOGGER.info(f"Deleted QA column {column_id} from dataset {dataset_id} in project {project_id}")

        return {"message": f"Deleted column {column_id} successfully"}
    except (QADatasetNotInProjectError, QAColumnNotFoundError):
        raise
    except Exception as e:
        LOGGER.error(f"Error in delete_qa_column_service: {str(e)}")
        raise QADatasetDeleteCustomColumnError(project_id, dataset_id, column_id, str(e)) from e
