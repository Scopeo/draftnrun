import logging
import uuid
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.quality_assurance_repository import (
    check_column_exist,
    check_dataset_belongs_to_organization,
    check_dataset_belongs_to_project,
    create_custom_column,
    delete_custom_column,
    get_dataset_custom_columns_display_max_position,
    get_qa_columns_by_dataset,
    remove_column_value_from_custom_column,
    rename_custom_column,
)
from ada_backend.schemas.qa_metadata_schema import QAColumnResponse
from ada_backend.services.qa.qa_error import (
    QAColumnNotFoundError,
    QADatasetNotInOrganizationError,
    QADatasetNotInProjectError,
)

LOGGER = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────

def _validate_dataset_ownership_org(session: Session, organization_id: UUID, dataset_id: UUID) -> None:
    if not check_dataset_belongs_to_organization(session, organization_id, dataset_id):
        raise QADatasetNotInOrganizationError(organization_id, dataset_id)


def _validate_dataset_ownership_project(session: Session, project_id: UUID, dataset_id: UUID) -> None:
    if not check_dataset_belongs_to_project(session, project_id, dataset_id):
        raise QADatasetNotInProjectError(project_id, dataset_id)


def _validate_column_exists(session: Session, dataset_id: UUID, column_id: UUID) -> None:
    if not check_column_exist(session, dataset_id, column_id):
        raise QAColumnNotFoundError(dataset_id, column_id)


# ── Core operations (ownership-agnostic) ──────────────────────────────

def _get_columns(session: Session, dataset_id: UUID) -> List[QAColumnResponse]:
    columns = get_qa_columns_by_dataset(session, dataset_id)
    return [QAColumnResponse.model_validate(col) for col in columns]


def _create_column(session: Session, dataset_id: UUID, column_name: str) -> QAColumnResponse:
    max_position = get_dataset_custom_columns_display_max_position(session, dataset_id)
    new_position = (max_position + 1) if max_position is not None else 0
    column_id = uuid.uuid4()
    qa_metadata = create_custom_column(
        session=session,
        dataset_id=dataset_id,
        column_id=column_id,
        column_name=column_name,
        column_display_position=new_position,
    )
    return QAColumnResponse.model_validate(qa_metadata)


def _rename_column(session: Session, dataset_id: UUID, column_id: UUID, column_name: str) -> QAColumnResponse:
    _validate_column_exists(session, dataset_id, column_id)
    qa_metadata = rename_custom_column(
        session=session,
        dataset_id=dataset_id,
        column_id=column_id,
        column_name=column_name,
    )
    return QAColumnResponse.model_validate(qa_metadata)


def _delete_column(session: Session, dataset_id: UUID, column_id: UUID) -> dict:
    _validate_column_exists(session, dataset_id, column_id)
    remove_column_value_from_custom_column(session, dataset_id, column_id)
    delete_custom_column(session, dataset_id, column_id)
    return {"message": f"Deleted column {column_id} successfully"}


# ── Organization-scoped public API ────────────────────────────────────

def get_qa_columns_by_dataset_service(
    session: Session, organization_id: UUID, dataset_id: UUID,
) -> List[QAColumnResponse]:
    _validate_dataset_ownership_org(session, organization_id, dataset_id)
    return _get_columns(session, dataset_id)


def create_qa_column_service(
    session: Session, organization_id: UUID, dataset_id: UUID, column_name: str,
) -> QAColumnResponse:
    _validate_dataset_ownership_org(session, organization_id, dataset_id)
    return _create_column(session, dataset_id, column_name)


def rename_qa_column_service(
    session: Session, organization_id: UUID, dataset_id: UUID, column_id: UUID, column_name: str,
) -> QAColumnResponse:
    _validate_dataset_ownership_org(session, organization_id, dataset_id)
    return _rename_column(session, dataset_id, column_id, column_name)


def delete_qa_column_service(
    session: Session, organization_id: UUID, dataset_id: UUID, column_id: UUID,
) -> dict:
    _validate_dataset_ownership_org(session, organization_id, dataset_id)
    return _delete_column(session, dataset_id, column_id)


# ── Deprecated project-scoped public API ──────────────────────────────

def get_qa_columns_by_dataset_project_service(
    session: Session, project_id: UUID, dataset_id: UUID,
) -> List[QAColumnResponse]:
    _validate_dataset_ownership_project(session, project_id, dataset_id)
    return _get_columns(session, dataset_id)


def create_qa_column_project_service(
    session: Session, project_id: UUID, dataset_id: UUID, column_name: str,
) -> QAColumnResponse:
    _validate_dataset_ownership_project(session, project_id, dataset_id)
    return _create_column(session, dataset_id, column_name)


def rename_qa_column_project_service(
    session: Session, project_id: UUID, dataset_id: UUID, column_id: UUID, column_name: str,
) -> QAColumnResponse:
    _validate_dataset_ownership_project(session, project_id, dataset_id)
    return _rename_column(session, dataset_id, column_id, column_name)


def delete_qa_column_project_service(
    session: Session, project_id: UUID, dataset_id: UUID, column_id: UUID,
) -> dict:
    _validate_dataset_ownership_project(session, project_id, dataset_id)
    return _delete_column(session, dataset_id, column_id)
