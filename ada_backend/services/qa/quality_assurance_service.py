import csv
import io
import json
import logging
from collections import Counter
from typing import BinaryIO, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import CallType
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.repositories.qa_evaluation_repository import delete_evaluations_for_input_ids
from ada_backend.repositories.quality_assurance_repository import (
    clear_version_outputs_for_input_ids,
    create_datasets,
    create_inputs_groundtruths,
    delete_datasets,
    delete_inputs_groundtruths,
    get_datasets_by_project,
    get_inputs_groundtruths_by_dataset,
    get_inputs_groundtruths_by_ids,
    get_inputs_groundtruths_count_by_dataset,
    get_outputs_by_graph_runner,
    get_positions_of_dataset,
    get_qa_columns_by_dataset,
    get_version_output_ids_by_input_ids_and_graph_runner,
    update_dataset,
    update_inputs_groundtruths,
    upsert_version_output,
)
from ada_backend.schemas.dataset_schema import (
    DatasetCreateList,
    DatasetDeleteList,
    DatasetListResponse,
    DatasetResponse,
)
from ada_backend.schemas.input_groundtruth_schema import (
    InputGroundtruthCreate,
    InputGroundtruthCreateList,
    InputGroundtruthDeleteList,
    InputGroundtruthResponse,
    InputGroundtruthResponseList,
    InputGroundtruthUpdateList,
    PaginatedInputGroundtruthResponse,
    Pagination,
    QARunRequest,
    QARunResponse,
    QARunResult,
    QARunSummary,
)
from ada_backend.services.agent_runner_service import run_agent
from ada_backend.services.errors import GraphNotBoundToProjectError
from ada_backend.services.metrics.utils import query_conversation_messages
from ada_backend.services.qa.csv_processing import get_headers_from_csv, process_csv
from ada_backend.services.qa.qa_error import (
    CSVEmptyFileError,
    CSVExportError,
    CSVInvalidJSONError,
    CSVInvalidPositionError,
    CSVMissingDatasetColumnError,
    CSVNonUniquePositionError,
    QADuplicatePositionError,
    QAPartialPositionError,
)
from ada_backend.services.qa.qa_metadata_service import create_qa_column_service

LOGGER = logging.getLogger(__name__)

MAX_CSV_EXPORT_SIZE_MB = 10
MAX_CSV_EXPORT_SIZE_BYTES = MAX_CSV_EXPORT_SIZE_MB * 1024 * 1024


def get_inputs_groundtruths_with_version_outputs_service(
    session: Session,
    dataset_id: UUID,
    page: int = 1,
    page_size: int = 100,
) -> PaginatedInputGroundtruthResponse:
    """Get input-groundtruth entries for a dataset without version outputs.

    Args:
        session: SQLAlchemy session
        dataset_id: ID of the dataset
        page: Page number (1-based)
        page_size: Number of items per page

    Returns:
        Paginated list of input-groundtruth entries without outputs
    """
    try:
        skip = (page - 1) * page_size
        number_of_inputs_outputs = get_inputs_groundtruths_count_by_dataset(session, dataset_id)
        number_of_pages = number_of_inputs_outputs // page_size + (
            1 if number_of_inputs_outputs % page_size > 0 else 0
        )
        inputs = get_inputs_groundtruths_by_dataset(session, dataset_id, skip, page_size)

        response_list = [InputGroundtruthResponse.model_validate(input_groundtruth) for input_groundtruth in inputs]

        return PaginatedInputGroundtruthResponse(
            pagination=Pagination(
                page=page,
                size=page_size,
                total_items=number_of_inputs_outputs,
                total_pages=number_of_pages,
            ),
            inputs_groundtruths=response_list,
        )
    except Exception as e:
        LOGGER.error(f"Error in get_inputs_groundtruths_with_version_outputs_service: {str(e)}")
        raise ValueError(f"Failed to get input-groundtruth entries with version outputs: {str(e)}") from e


def get_outputs_by_graph_runner_service(
    session: Session,
    dataset_id: UUID,
    graph_runner_id: UUID,
) -> Dict[UUID, str]:
    """Get outputs for a specific graph_runner.

    Args:
        session: SQLAlchemy session
        dataset_id: ID of the dataset
        graph_runner_id: ID of the graph runner

    Returns:
        Dictionary mapping input_id (as UUID) to output (as string)
    """
    try:
        outputs = get_outputs_by_graph_runner(session, dataset_id, graph_runner_id)
        return {input_id: output for input_id, output in outputs}
    except Exception as e:
        LOGGER.error(f"Error in get_outputs_by_graph_runner_service: {str(e)}")
        raise ValueError(f"Failed to get outputs for graph runner: {str(e)}") from e


def get_version_output_ids_by_input_ids_and_graph_runner_service(
    session: Session,
    input_ids: List[UUID],
    graph_runner_id: UUID,
) -> Dict[UUID, Optional[UUID]]:
    return get_version_output_ids_by_input_ids_and_graph_runner(
        session=session, input_ids=input_ids, graph_runner_id=graph_runner_id
    )


async def run_qa_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    run_request: QARunRequest,
) -> QARunResponse:
    """Run QA process on multiple inputs and store results in VersionOutput table.

    Args:
        session: SQLAlchemy session
        project_id: ID of the project to run
        dataset_id: ID of the dataset
        run_request: Request containing graph_runner_id and either input_ids or run_all flag

    Returns:
        Results of the QA run with summary
    """
    try:
        if run_request.run_all:
            number_of_dataset_inputs = get_inputs_groundtruths_count_by_dataset(session, dataset_id)
            input_entries = get_inputs_groundtruths_by_dataset(
                session, dataset_id, skip=0, limit=number_of_dataset_inputs
            )
            if not input_entries:
                raise ValueError(f"No input entries found in dataset {dataset_id}")
        else:
            input_entries = get_inputs_groundtruths_by_ids(session, run_request.input_ids)
            if not input_entries:
                raise ValueError("No input entries found for the provided input_ids")

            for entry in input_entries:
                if entry.dataset_id != dataset_id:
                    raise ValueError(f"Input {entry.id} does not belong to dataset {dataset_id}")

        results = []
        successful_runs = 0
        failed_runs = 0

        env_relationship = get_env_relationship_by_graph_runner_id(
            session=session, graph_runner_id=run_request.graph_runner_id
        )
        if not env_relationship:
            raise GraphNotBoundToProjectError(run_request.graph_runner_id)
        environment = env_relationship.environment
        for input_entry in input_entries:
            try:
                chat_response = await run_agent(
                    session=session,
                    project_id=project_id,
                    graph_runner_id=run_request.graph_runner_id,
                    input_data=input_entry.input,
                    environment=environment,
                    call_type=CallType.QA,
                )

                output_content = chat_response.message
                if chat_response.error:
                    output_content = f"Error: {chat_response.error}"

                upsert_version_output(
                    session=session,
                    input_id=input_entry.id,
                    output=output_content,
                    graph_runner_id=run_request.graph_runner_id,
                )

                result = QARunResult(
                    input_id=input_entry.id,
                    input=input_entry.input,
                    groundtruth=input_entry.groundtruth,
                    output=output_content,
                    graph_runner_id=run_request.graph_runner_id,
                    success=True,
                    error=None,
                )

                successful_runs += 1

            except Exception as e:
                LOGGER.error(f"Error processing input {input_entry.id}: {str(e)}")

                error_output = f"Error: {str(e)}"
                upsert_version_output(
                    session=session,
                    input_id=input_entry.id,
                    output=error_output,
                    graph_runner_id=run_request.graph_runner_id,
                )

                result = QARunResult(
                    input_id=input_entry.id,
                    input=input_entry.input,
                    groundtruth=input_entry.groundtruth,
                    output=error_output,
                    graph_runner_id=run_request.graph_runner_id,
                    success=False,
                    error=str(e),
                )

                failed_runs += 1

            results.append(result)

        total_processed = len(results)
        success_rate = (successful_runs / total_processed * 100) if total_processed > 0 else 0.0

        summary = QARunSummary(
            total=total_processed,
            passed=successful_runs,
            failed=failed_runs,
            success_rate=success_rate,
        )

        run_mode = "all entries" if run_request.run_all else f"{len(run_request.input_ids)} selected entries"
        LOGGER.info(
            f"QA run completed for project {project_id}, "
            f"dataset {dataset_id}, graph_runner_id {run_request.graph_runner_id}, mode: {run_mode}"
        )
        LOGGER.info(
            f"Total processed: {total_processed}, Successful: {successful_runs}, "
            f"Failed: {failed_runs}, Success Rate: {success_rate:.2f}%"
        )

        return QARunResponse(
            results=results,
            summary=summary,
        )

    except Exception as e:
        LOGGER.error(f"Error in run_qa_service: {str(e)}")
        raise ValueError(f"Failed to run QA process: {str(e)}") from e


def create_inputs_groundtruths_service(
    session: Session,
    dataset_id: UUID,
    inputs_groundtruths_data: InputGroundtruthCreateList,
) -> InputGroundtruthResponseList:
    """
    Create input-groundtruth entries.

    Args:
        session (Session): SQLAlchemy session
        dataset_id (UUID): ID of the dataset
        inputs_groundtruths_data (InputGroundtruthCreateList): Input-groundtruth data to create

    Returns:
        InputGroundtruthResponseList: The created input-groundtruth entries
    """
    try:
        current_dataset_positions = get_positions_of_dataset(session, dataset_id)
        inputs_positions = [
            input_groundtruth.position
            for input_groundtruth in inputs_groundtruths_data.inputs_groundtruths
            if input_groundtruth.position is not None
        ]
        if inputs_positions and len(inputs_positions) != len(inputs_groundtruths_data.inputs_groundtruths):
            raise QAPartialPositionError()
        duplicated_positions = _get_duplicate_positions(current_dataset_positions + inputs_positions)
        if len(duplicated_positions) > 0:
            raise QADuplicatePositionError(duplicated_positions)
        created_inputs_groundtruths = create_inputs_groundtruths(
            session,
            dataset_id,
            inputs_groundtruths_data.inputs_groundtruths,
        )

        LOGGER.info(f"Created {len(created_inputs_groundtruths)} input-groundtruth entries for dataset {dataset_id}")

        return InputGroundtruthResponseList(
            inputs_groundtruths=[InputGroundtruthResponse.model_validate(ig) for ig in created_inputs_groundtruths]
        )
    except (QADuplicatePositionError, QAPartialPositionError):
        raise
    except Exception as e:
        LOGGER.error(f"Error in create_inputs_groundtruths_service: {str(e)}")
        raise ValueError(f"Failed to create input-groundtruth entries: {str(e)}") from e


def update_inputs_groundtruths_service(
    session: Session,
    dataset_id: UUID,
    inputs_groundtruths_data: InputGroundtruthUpdateList,
) -> InputGroundtruthResponseList:
    """
    Update multiple input-groundtruth entries.

    Args:
        session (Session): SQLAlchemy session
        dataset_id (UUID): ID of the dataset
        inputs_groundtruths_data (InputGroundtruthUpdateList): Input-groundtruth data to update

    Returns:
        InputGroundtruthResponseList: The updated input-groundtruth entries
    """
    try:
        # Prepare updates data
        updates_data = [
            (ig.id, ig.input, ig.groundtruth, ig.custom_columns) for ig in inputs_groundtruths_data.inputs_groundtruths
        ]

        updated_inputs_groundtruths = update_inputs_groundtruths(
            session,
            updates_data,
            dataset_id,
        )

        # If any input texts were updated, clear corresponding version outputs across all versions
        input_ids_changed = [ig.id for ig in inputs_groundtruths_data.inputs_groundtruths if ig.input is not None]
        if input_ids_changed:
            cleared_count = clear_version_outputs_for_input_ids(session, input_ids_changed)
            deleted_evals = delete_evaluations_for_input_ids(session, input_ids_changed)
            LOGGER.info(
                f"Cleared {cleared_count} outputs and deleted {deleted_evals} evaluations "
                f"for {len(input_ids_changed)} inputs"
            )

        session.commit()

        LOGGER.info(f"Updated {len(updated_inputs_groundtruths)} input-groundtruth entries for dataset {dataset_id}")

        return InputGroundtruthResponseList(
            inputs_groundtruths=[InputGroundtruthResponse.model_validate(ig) for ig in updated_inputs_groundtruths]
        )
    except Exception as e:
        session.rollback()
        LOGGER.error(f"Error in update_inputs_groundtruths_service: {str(e)}")
        raise ValueError(f"Failed to update input-groundtruth entries: {str(e)}") from e


def delete_inputs_groundtruths_service(
    session: Session,
    dataset_id: UUID,
    delete_data: InputGroundtruthDeleteList,
) -> int:
    """
    Delete multiple input-groundtruth entries.

    Args:
        session (Session): SQLAlchemy session
        dataset_id (UUID): ID of the dataset
        delete_data (InputGroundtruthDeleteList): IDs of entries to delete

    Returns:
        int: Number of deleted entries
    """
    try:
        deleted_count = delete_inputs_groundtruths(
            session,
            delete_data.input_groundtruth_ids,
            dataset_id,
        )

        LOGGER.info(f"Deleted {deleted_count} input-groundtruth entries for dataset {dataset_id}")

        return deleted_count
    except Exception as e:
        LOGGER.error(f"Error in delete_inputs_groundtruths_service: {str(e)}")
        raise ValueError(f"Failed to delete input-groundtruth entries: {str(e)}") from e


def get_datasets_by_project_service(
    session: Session,
    project_id: UUID,
) -> List[DatasetResponse]:
    """
    Get all datasets for a project.

    Args:
        session (Session): SQLAlchemy session
        project_id (UUID): ID of the project

    Returns:
        List[DatasetResponse]: List of datasets
    """
    try:
        datasets = get_datasets_by_project(session, project_id)
        return [DatasetResponse.model_validate(dataset) for dataset in datasets]
    except Exception as e:
        LOGGER.error(f"Error in get_datasets_by_project_service: {str(e)}")
        raise ValueError(f"Failed to get datasets: {str(e)}") from e


def create_datasets_service(
    session: Session,
    project_id: UUID,
    datasets_data: DatasetCreateList,
) -> DatasetListResponse:
    """
    Create datasets.

    Args:
        session (Session): SQLAlchemy session
        project_id (UUID): ID of the project
        datasets_data (DatasetCreateList): Dataset data to create

    Returns:
        DatasetListResponse: The created datasets
    """
    try:
        created_datasets = create_datasets(
            session,
            project_id,
            datasets_data.datasets_name,
        )

        LOGGER.info(f"Created {len(created_datasets)} datasets for project {project_id}")
        return DatasetListResponse(datasets=[DatasetResponse.model_validate(dataset) for dataset in created_datasets])
    except Exception as e:
        LOGGER.error(f"Error in create_datasets_service: {str(e)}")
        raise ValueError(f"Failed to create datasets: {str(e)}") from e


def update_dataset_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    dataset_name: str,
) -> DatasetResponse:
    """
    Update a single dataset.

    Args:
        session (Session): SQLAlchemy session
        project_id (UUID): ID of the project
        dataset_id (UUID): ID of the dataset to update
        dataset_name (str): New name for the dataset

    Returns:
        DatasetResponse: The updated dataset
    """
    try:
        updated_dataset = update_dataset(
            session,
            dataset_id,
            dataset_name,
            project_id,
        )

        LOGGER.info(f"Updated dataset {dataset_id} with name '{dataset_name}' for project {project_id}")
        return DatasetResponse.model_validate(updated_dataset)
    except Exception as e:
        LOGGER.error(f"Error in update_dataset_service: {str(e)}")
        raise ValueError(f"Failed to update dataset: {str(e)}") from e


def delete_datasets_service(
    session: Session,
    project_id: UUID,
    delete_data: DatasetDeleteList,
) -> int:
    """
    Delete multiple datasets.

    Args:
        session (Session): SQLAlchemy session
        project_id (UUID): ID of the project
        delete_data (DatasetDeleteList): IDs of datasets to delete

    Returns:
        int: Number of deleted datasets
    """
    try:
        deleted_count = delete_datasets(
            session,
            delete_data.dataset_ids,
            project_id,
        )

        LOGGER.info(f"Deleted {deleted_count} datasets for project {project_id}")
        return deleted_count
    except Exception as e:
        LOGGER.error(f"Error in delete_datasets_service: {str(e)}")
        raise ValueError(f"Failed to delete datasets: {str(e)}") from e


def save_conversation_to_groundtruth_service(
    session: Session,
    trace_id: str,
    dataset_id: UUID,
) -> List[InputGroundtruthResponse]:
    input_payload, output_payload = query_conversation_messages(trace_id)
    if not input_payload and not output_payload:
        LOGGER.error(
            "Trace %s not found or contains no messages while saving to dataset %s.",
            trace_id,
            dataset_id,
        )
    input_payload.pop("conversation_id", None)
    input_entry = InputGroundtruthCreate(input=input_payload, groundtruth=output_payload["messages"][-1]["content"])
    input_groundtruth_response_list = create_inputs_groundtruths_service(
        session, dataset_id, InputGroundtruthCreateList(inputs_groundtruths=[input_entry])
    )
    return input_groundtruth_response_list.inputs_groundtruths


def export_qa_data_to_csv_service(
    session: Session,
    dataset_id: UUID,
    graph_runner_id: UUID,
) -> str:
    try:
        total_count = get_inputs_groundtruths_count_by_dataset(session, dataset_id)
        if total_count == 0:
            raise CSVExportError(dataset_id, "No data to export. Dataset is empty.")

        input_entries = get_inputs_groundtruths_by_dataset(session, dataset_id, skip=0, limit=total_count)
        outputs_dict = dict(get_outputs_by_graph_runner(session, dataset_id, graph_runner_id))

        # Get custom columns for the dataset (already sorted by index_position)
        custom_columns = get_qa_columns_by_dataset(session, dataset_id)

        # Build header row: standard columns + custom column names
        header_row = ["position", "input", "expected_output", "actual_output"]
        custom_column_names = [col.column_name for col in custom_columns]
        header_row.extend(custom_column_names)

        # Create mapping from column_name to column_id (as string) for value lookup
        column_name_to_id = {col.column_name: str(col.column_id) for col in custom_columns}

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header_row)

        for entry in input_entries:
            input_str = json.dumps(entry.input) if entry.input else ""
            groundtruth_str = entry.groundtruth if entry.groundtruth is not None else ""
            output_str = outputs_dict.get(entry.id, "") if entry.id in outputs_dict else ""
            position_str = str(entry.position) if entry.position is not None else ""

            row = [position_str, input_str, groundtruth_str, output_str]

            custom_columns_dict = entry.custom_columns if entry.custom_columns else {}
            for column_name in custom_column_names:
                column_id = column_name_to_id[column_name]
                value = custom_columns_dict.get(column_id, "")
                if value is None:
                    value = ""
                row.append(value)

            writer.writerow(row)

        csv_content = output.getvalue()
        output.close()

        csv_size_bytes = len(csv_content.encode("utf-8"))
        if csv_size_bytes > MAX_CSV_EXPORT_SIZE_BYTES:
            raise CSVExportError(
                dataset_id, f"CSV file too large to export. Maximum {MAX_CSV_EXPORT_SIZE_MB} MB allowed."
            )

        LOGGER.info(
            f"Exported {len(input_entries)} QA data entries to CSV for dataset {dataset_id} "
            f"(graph_runner_id={graph_runner_id}) with {len(custom_columns)} custom columns"
        )
        return csv_content
    except Exception as e:
        LOGGER.error(f"Error in export_qa_data_to_csv_service: {str(e)}")
        raise e


def import_qa_data_from_csv_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    csv_file: BinaryIO,
) -> InputGroundtruthResponseList:
    try:
        headers_from_csv = get_headers_from_csv(csv_file)
        expected_columns = {"input", "expected_output", "actual_output", "position"}
        custom_columns_from_csv = set(headers_from_csv) - expected_columns
        dataset_custom_columns = get_qa_columns_by_dataset(session, dataset_id)
        dataset_column_names = {col.column_name for col in dataset_custom_columns}

        missing_custom_columns_from_csv = dataset_column_names - custom_columns_from_csv

        if missing_custom_columns_from_csv:
            raise CSVMissingDatasetColumnError(
                column=",".join(missing_custom_columns_from_csv),
                found_columns=list(custom_columns_from_csv),
                required_columns=list(dataset_column_names),
            )

        custom_columns_to_add = custom_columns_from_csv - dataset_column_names
        for column_name in custom_columns_to_add:
            create_qa_column_service(
                session=session,
                project_id=project_id,
                dataset_id=dataset_id,
                column_name=column_name,
            )

        updated_dataset_custom_columns_list = get_qa_columns_by_dataset(session, dataset_id)
        updated_dataset_custom_columns = {
            str(col.column_id): col.column_name for col in updated_dataset_custom_columns_list
        }

        inputs_groundtruths_data_to_create = []
        for row_data in process_csv(csv_file, custom_columns_mapping=updated_dataset_custom_columns):
            inputs_groundtruths_data_to_create.append(
                InputGroundtruthCreate(
                    input=row_data["input"],
                    groundtruth=row_data["expected_output"] if row_data["expected_output"] else None,
                    position=row_data["position"],
                    custom_columns=row_data["custom_columns"],
                )
            )

        if not inputs_groundtruths_data_to_create:
            raise CSVEmptyFileError()

        created_inputs_groundtruths = create_inputs_groundtruths_service(
            session=session,
            dataset_id=dataset_id,
            inputs_groundtruths_data=InputGroundtruthCreateList(
                inputs_groundtruths=inputs_groundtruths_data_to_create
            ),
        )

        LOGGER.info(
            f"Imported {len(created_inputs_groundtruths.inputs_groundtruths)} input-groundtruth "
            f"entries from CSV for dataset {dataset_id}"
        )

        return created_inputs_groundtruths
    except QADuplicatePositionError as e:
        LOGGER.error(f"Error in import_qa_data_from_csv_service: {str(e)}")
        raise CSVNonUniquePositionError(duplicate_positions=e.duplicate_positions) from e
    except (
        CSVEmptyFileError,
        CSVMissingDatasetColumnError,
        CSVInvalidJSONError,
        CSVInvalidPositionError,
    ) as e:
        LOGGER.error(f"Error in import_qa_data_from_csv_service: {str(e)}")
        raise e


def _get_duplicate_positions(positions: List[int]) -> List[int]:
    duplicated_positions = [item for item, count in Counter(positions).items() if count > 1]
    return duplicated_positions
