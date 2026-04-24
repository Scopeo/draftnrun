import json
import logging
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from ada_backend.database.models import (
    AssociationColumnMapping,
    ColumnRole,
    DatasetCellValue,
    DatasetProject,
    DatasetProjectAssociation,
    InputGroundtruth,
    QADatasetMetadata,
    VersionOutput,
)
from ada_backend.schemas.input_groundtruth_schema import (
    InputGroundtruthCreate,
    InputGroundtruthUpdateList,
    InputGroundtruthUpdateWithId,
)

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
    """Create multiple input-groundtruth entries with dual-write to DatasetCellValue."""
    max_position = get_max_position_of_dataset(session, dataset_id)
    starting_position = (max_position + 1) if max_position is not None else 1

    positions = [
        data.position if data.position is not None else starting_position + i
        for i, data in enumerate(inputs_groundtruths_data)
    ]

    column_map = _get_typed_column_map(session, dataset_id)

    inputs_groundtruths = []
    for data, position in zip(inputs_groundtruths_data, positions, strict=False):
        input_val, groundtruth_val = _resolve_legacy_from_cell_values(data, column_map)
        ig = InputGroundtruth(
            dataset_id=dataset_id,
            input=input_val,
            groundtruth=groundtruth_val,
            position=position,
            custom_columns=data.custom_columns,
        )
        inputs_groundtruths.append(ig)

    session.add_all(inputs_groundtruths)
    session.flush()

    for ig, data in zip(inputs_groundtruths, inputs_groundtruths_data, strict=False):
        cell_vals = _build_cell_values_for_write(data, column_map)
        if cell_vals:
            _upsert_cell_values(session, ig.id, cell_vals)

    session.commit()

    for ig in inputs_groundtruths:
        session.refresh(ig)

    LOGGER.info(f"Created {len(inputs_groundtruths)} input-groundtruth entries for dataset {dataset_id}")
    return inputs_groundtruths


def update_inputs_groundtruths(
    session: Session,
    inputs_groundtruths_data: InputGroundtruthUpdateList,
    dataset_id: UUID,
) -> List[InputGroundtruth]:
    """Update multiple input-groundtruth entries with dual-write to DatasetCellValue."""
    updated_inputs_groundtruths = []
    column_map = _get_typed_column_map(session, dataset_id)

    for update_item in inputs_groundtruths_data.inputs_groundtruths:
        input_id = update_item.id
        input_data = update_item.input
        groundtruth = update_item.groundtruth
        custom_columns = update_item.custom_columns
        input_groundtruth = (
            session.query(InputGroundtruth)
            .filter(InputGroundtruth.id == input_id, InputGroundtruth.dataset_id == dataset_id)
            .first()
        )

        if input_groundtruth:
            if input_data is not None:
                input_groundtruth.input = input_data
            if groundtruth is not None:
                input_groundtruth.groundtruth = groundtruth
            if custom_columns is not None:
                current_custom_columns = (input_groundtruth.custom_columns or {}).copy()
                for key, value in custom_columns.items():
                    if value is None:
                        current_custom_columns.pop(key, None)
                    else:
                        current_custom_columns[key] = value
                input_groundtruth.custom_columns = current_custom_columns if current_custom_columns else None

            cell_updates = _build_cell_values_for_update(update_item, column_map)
            if cell_updates:
                _upsert_cell_values(session, input_id, cell_updates)

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
    qa_session_id: Optional[UUID] = None,
) -> VersionOutput:
    """Create or update a version output entry.

    When qa_session_id is given the lookup key is (input_id, qa_session_id) so
    each QA session stores its own isolated row.  When qa_session_id is None
    (sync runs) the legacy (input_id, graph_runner_id) key is used.
    """
    if qa_session_id is not None:
        existing: Optional[VersionOutput] = (
            session.query(VersionOutput)
            .filter(VersionOutput.input_id == input_id, VersionOutput.qa_session_id == qa_session_id)
            .first()
        )
    else:
        existing = (
            session.query(VersionOutput)
            .filter(
                VersionOutput.input_id == input_id,
                VersionOutput.graph_runner_id == graph_runner_id,
                VersionOutput.qa_session_id.is_(None),
            )
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
        qa_session_id=qa_session_id,
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


def get_outputs_by_session(
    session: Session,
    qa_session_id: UUID,
) -> List[Tuple[UUID, str]]:
    return (
        session.query(VersionOutput.input_id, VersionOutput.output)
        .filter(VersionOutput.qa_session_id == qa_session_id)
        .all()
    )


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


# Dataset functions (project-scoped — kept for backward compatibility, will be removed in a follow-up PR)
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


# Dataset functions (organization-scoped)
def get_datasets_by_organization(
    session: Session,
    organization_id: UUID,
    skip: int = 0,
    limit: int = 100,
) -> List[DatasetProject]:
    """Get datasets for an organization with pagination."""
    return (
        session.query(DatasetProject)
        .filter(DatasetProject.organization_id == organization_id)
        .order_by(DatasetProject.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


# TODO: remove when system columns are no longer hardcoded (users will define their own roles)
def _create_system_columns(session: Session, dataset_id: UUID) -> None:
    session.add(QADatasetMetadata(
        dataset_id=dataset_id, column_name="Input", column_display_position=0, default_role=ColumnRole.INPUT,
    ))
    session.add(QADatasetMetadata(
        dataset_id=dataset_id,
        column_name="Expected Output",
        column_display_position=1,
        default_role=ColumnRole.EXPECTED_OUTPUT,
    ))


def create_datasets(
    session: Session,
    organization_id: UUID,
    dataset_names: List[str],
    *,
    commit: bool = True,
) -> List[DatasetProject]:
    datasets = []

    for dataset_name in dataset_names:
        dataset = DatasetProject(
            organization_id=organization_id,
            dataset_name=dataset_name,
        )
        datasets.append(dataset)

    session.add_all(datasets)
    session.flush()

    for dataset in datasets:
        _create_system_columns(session, dataset.id)

    if commit:
        session.commit()
        for dataset in datasets:
            session.refresh(dataset)

    LOGGER.debug(f"Created {len(datasets)} datasets for organization {organization_id}")
    return datasets


def update_dataset(
    session: Session,
    dataset_id: UUID,
    dataset_name: Optional[str],
    organization_id: UUID,
) -> DatasetProject:
    """Update a dataset"""
    dataset = (
        session.query(DatasetProject)
        .filter(DatasetProject.id == dataset_id, DatasetProject.organization_id == organization_id)
        .first()
    )

    if dataset_name is not None:
        dataset.dataset_name = dataset_name

    session.commit()

    LOGGER.debug(f"Updated dataset {dataset_id} with name '{dataset_name}' for organization {organization_id}")
    return dataset


def delete_datasets(
    session: Session,
    dataset_ids: List[UUID],
    organization_id: UUID,
) -> int:
    """Delete multiple datasets."""
    deleted_count = (
        session.query(DatasetProject)
        .filter(DatasetProject.id.in_(dataset_ids), DatasetProject.organization_id == organization_id)
        .delete(synchronize_session=False)
    )

    session.commit()

    LOGGER.info(f"Deleted {deleted_count} datasets for organization {organization_id}")
    return deleted_count


def check_dataset_belongs_to_organization(session: Session, organization_id: UUID, dataset_id: UUID) -> bool:
    exists = session.query(
        session.query(DatasetProject)
        .filter(DatasetProject.id == dataset_id, DatasetProject.organization_id == organization_id)
        .exists()
    ).scalar()
    return exists


def check_dataset_belongs_to_project(session: Session, project_id: UUID, dataset_id: UUID) -> bool:
    exists = session.query(
        session.query(DatasetProjectAssociation)
        .filter(DatasetProjectAssociation.dataset_id == dataset_id, DatasetProjectAssociation.project_id == project_id)
        .exists()
    ).scalar()
    return exists


# Dataset-Project association functions
def get_dataset_project_associations(session: Session, dataset_id: UUID) -> List[UUID]:
    """Get project IDs associated with a dataset."""
    return [
        row[0]
        for row in session.query(DatasetProjectAssociation.project_id)
        .filter(DatasetProjectAssociation.dataset_id == dataset_id)
        .all()
    ]


def set_dataset_project_associations(
    session: Session,
    dataset_id: UUID,
    project_ids: List[UUID],
) -> None:
    """Replace all project associations for a dataset, auto-populating column mappings from system columns."""
    session.query(DatasetProjectAssociation).filter(DatasetProjectAssociation.dataset_id == dataset_id).delete(
        synchronize_session=False
    )

    system_columns = (
        session.query(QADatasetMetadata)
        .filter(QADatasetMetadata.dataset_id == dataset_id, QADatasetMetadata.default_role.isnot(None))
        .all()
    )

    associations = [DatasetProjectAssociation(dataset_id=dataset_id, project_id=pid) for pid in project_ids]
    session.add_all(associations)
    session.flush()

    mappings = [
        AssociationColumnMapping(association_id=assoc.id, column_id=col.column_id, role=col.default_role)
        for assoc in associations
        for col in system_columns
    ]
    session.add_all(mappings)

    session.commit()


def create_column_mappings_for_association(
    session: Session, association_id: UUID, dataset_id: UUID,
) -> List[AssociationColumnMapping]:
    system_columns = (
        session.query(QADatasetMetadata)
        .filter(QADatasetMetadata.dataset_id == dataset_id, QADatasetMetadata.default_role.isnot(None))
        .all()
    )
    mappings = []
    for col in system_columns:
        mapping = AssociationColumnMapping(
            association_id=association_id, column_id=col.column_id, role=col.default_role,
        )
        session.add(mapping)
        mappings.append(mapping)
    return mappings


def get_column_mappings_for_association(
    session: Session, association_id: UUID,
) -> List[AssociationColumnMapping]:
    return (
        session.query(AssociationColumnMapping)
        .filter(AssociationColumnMapping.association_id == association_id)
        .all()
    )


def remove_column_mapping(session: Session, association_id: UUID, column_id: UUID) -> None:
    session.query(AssociationColumnMapping).filter(
        AssociationColumnMapping.association_id == association_id,
        AssociationColumnMapping.column_id == column_id,
    ).delete(synchronize_session=False)


def get_qa_columns_by_dataset(
    session: Session, dataset_id: UUID, *, user_only: bool = False,
) -> List[QADatasetMetadata]:
    query = session.query(QADatasetMetadata).filter(QADatasetMetadata.dataset_id == dataset_id)
    if user_only:
        query = query.filter(QADatasetMetadata.default_role.is_(None))
    return query.order_by(QADatasetMetadata.column_display_position.asc()).all()


def get_dataset_custom_columns_display_max_position(
    session: Session,
    dataset_id: UUID,
) -> Optional[int]:
    max_position = (
        session.query(func.max(QADatasetMetadata.column_display_position))
        .filter(QADatasetMetadata.dataset_id == dataset_id)
        .scalar()
    )
    return max_position


def create_custom_column(
    session: Session,
    dataset_id: UUID,
    column_id: UUID,
    column_name: str,
    column_display_position: int,
    default_role: Optional["ColumnRole"] = None,
) -> QADatasetMetadata:
    qa_metadata = QADatasetMetadata(
        dataset_id=dataset_id,
        column_id=column_id,
        column_name=column_name,
        column_display_position=column_display_position,
        default_role=default_role,
    )

    session.add(qa_metadata)
    session.commit()
    session.refresh(qa_metadata)

    LOGGER.info(
        f"Created QA column '{column_name}' (column_id: {column_id}, default_role: {default_role}) "
        f"at position {column_display_position} for dataset {dataset_id}"
    )
    return qa_metadata


def check_column_exist(session: Session, dataset_id: UUID, column_id: UUID) -> bool:
    exists = session.query(
        session.query(QADatasetMetadata)
        .filter(QADatasetMetadata.dataset_id == dataset_id, QADatasetMetadata.column_id == column_id)
        .exists()
    ).scalar()
    return exists


def get_column_metadata(session: Session, dataset_id: UUID, column_id: UUID) -> Optional[QADatasetMetadata]:
    return (
        session.query(QADatasetMetadata)
        .filter(QADatasetMetadata.dataset_id == dataset_id, QADatasetMetadata.column_id == column_id)
        .first()
    )


def rename_custom_column(
    session: Session,
    dataset_id: UUID,
    column_id: UUID,
    column_name: str,
) -> QADatasetMetadata:
    qa_metadata = (
        session.query(QADatasetMetadata)
        .filter(QADatasetMetadata.dataset_id == dataset_id, QADatasetMetadata.column_id == column_id)
        .first()
    )

    qa_metadata.column_name = column_name
    session.commit()
    session.refresh(qa_metadata)

    return qa_metadata


def delete_custom_column(session: Session, dataset_id: UUID, column_id: UUID) -> None:
    column_id_str = str(column_id)

    remove_key_from_jsonb = InputGroundtruth.custom_columns.op("-")(column_id_str)
    jsonb_empty_dict = func.cast("{}", JSONB)

    session.execute(
        update(InputGroundtruth)
        .where(
            InputGroundtruth.dataset_id == dataset_id,
            InputGroundtruth.custom_columns.isnot(None),
            InputGroundtruth.custom_columns.has_key(column_id_str),
        )
        .values(
            custom_columns=case(
                (func.cast(remove_key_from_jsonb, JSONB) == jsonb_empty_dict, None),
                else_=remove_key_from_jsonb,
            )
        )
    )

    session.query(DatasetCellValue).filter(DatasetCellValue.column_id == column_id).delete(
        synchronize_session=False
    )
    session.query(AssociationColumnMapping).filter(
        AssociationColumnMapping.column_id == column_id
    ).delete(synchronize_session=False)
    session.query(QADatasetMetadata).filter(
        QADatasetMetadata.dataset_id == dataset_id, QADatasetMetadata.column_id == column_id
    ).delete(synchronize_session=False)

    session.commit()


# ── DatasetCellValue helpers ──────────────────────────────────────────

def get_cell_values_for_rows(session: Session, row_ids: List[UUID]) -> Dict[UUID, Dict[str, Optional[str]]]:
    """Fetch cell values grouped by row_id."""
    if not row_ids:
        return {}
    rows = (
        session.query(DatasetCellValue.row_id, DatasetCellValue.column_id, DatasetCellValue.value)
        .filter(DatasetCellValue.row_id.in_(row_ids))
        .all()
    )
    result: Dict[UUID, Dict[str, Optional[str]]] = {}
    for row_id, col_id, value in rows:
        result.setdefault(row_id, {})[str(col_id)] = value
    return result


def _upsert_cell_values(session: Session, row_id: UUID, cell_values: Dict[str, Optional[str]]) -> None:
    """Insert or update cell values for a given row."""
    for col_id_str, value in cell_values.items():
        col_id = UUID(col_id_str)
        existing = (
            session.query(DatasetCellValue)
            .filter(DatasetCellValue.row_id == row_id, DatasetCellValue.column_id == col_id)
            .first()
        )
        if existing:
            existing.value = value
        else:
            session.add(DatasetCellValue(row_id=row_id, column_id=col_id, value=value))


def delete_cell_values_for_row(session: Session, row_id: UUID) -> int:
    return (
        session.query(DatasetCellValue)
        .filter(DatasetCellValue.row_id == row_id)
        .delete(synchronize_session=False)
    )


def _get_typed_column_map(session: Session, dataset_id: UUID) -> Dict[str, List["QADatasetMetadata"]]:
    """Return a dict mapping default_role -> list of columns for typed columns."""
    columns = get_qa_columns_by_dataset(session, dataset_id)
    result = {}
    for col in columns:
        if col.default_role is not None:
            role_key = col.default_role.value if hasattr(col.default_role, "value") else col.default_role
            result.setdefault(role_key, []).append(col)
    return result


def _resolve_legacy_from_cell_values(
    data: InputGroundtruthCreate,
    column_map: Dict,
) -> tuple[dict, Optional[str]]:
    """Derive legacy input/groundtruth from cell_values when not explicitly provided."""
    input_val = data.input
    groundtruth_val = data.groundtruth

    if data.cell_values:
        if input_val is None:
            for col in column_map.get("input", []):
                cv = data.cell_values.get(str(col.column_id))
                if cv is not None:
                    try:
                        input_val = json.loads(cv)
                    except (json.JSONDecodeError, TypeError):
                        input_val = {"value": cv}
                    break
        if groundtruth_val is None:
            for col in column_map.get("expected_output", []):
                cv = data.cell_values.get(str(col.column_id))
                if cv is not None:
                    groundtruth_val = cv
                    break

    if input_val is None:
        input_val = {}

    return input_val, groundtruth_val


def _build_cell_values_for_write(
    data: InputGroundtruthCreate,
    column_map: Dict,
) -> Dict[str, Optional[str]]:
    """Build cell_values dict from a create request, for dual-write."""
    cell_vals: Dict[str, Optional[str]] = {}

    for col in column_map.get("input", []):
        if data.input is not None:
            cell_vals[str(col.column_id)] = json.dumps(data.input)

    for col in column_map.get("expected_output", []):
        cell_vals[str(col.column_id)] = data.groundtruth

    if data.custom_columns:
        for col_id_str, value in data.custom_columns.items():
            cell_vals[col_id_str] = value

    if data.cell_values:
        cell_vals.update(data.cell_values)

    return cell_vals


def _build_cell_values_for_update(
    data: InputGroundtruthUpdateWithId,
    column_map: Dict,
) -> Dict[str, Optional[str]]:
    """Build cell_values dict from an update request, for dual-write."""
    cell_vals: Dict[str, Optional[str]] = {}

    if data.input is not None:
        for col in column_map.get("input", []):
            cell_vals[str(col.column_id)] = json.dumps(data.input)

    if data.groundtruth is not None:
        for col in column_map.get("expected_output", []):
            cell_vals[str(col.column_id)] = data.groundtruth

    if data.custom_columns:
        for col_id_str, value in data.custom_columns.items():
            cell_vals[col_id_str] = value

    if data.cell_values:
        cell_vals.update(data.cell_values)

    return cell_vals
