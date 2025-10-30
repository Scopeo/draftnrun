import logging
from typing import Dict, List
from uuid import UUID
import json

from sqlalchemy.orm import Session

from ada_backend.repositories.quality_assurance_repository import (
    create_inputs_groundtruths,
    update_inputs_groundtruths,
    delete_inputs_groundtruths,
    get_inputs_groundtruths_by_ids,
    get_inputs_groundtruths_by_dataset,
    get_inputs_groundtruths_count_by_dataset,
    upsert_version_output,
    create_datasets,
    update_dataset,
    delete_datasets,
    get_datasets_by_project,
    clear_version_outputs_for_input_ids,
    get_outputs_by_graph_runner,
)
from ada_backend.schemas.input_groundtruth_schema import (
    InputGroundtruthResponse,
    InputGroundtruthCreateList,
    InputGroundtruthUpdateList,
    InputGroundtruthDeleteList,
    InputGroundtruthResponseList,
    Pagination,
    PaginatedInputGroundtruthResponse,
    QARunRequest,
    QARunResult,
    QARunResponse,
    QARunSummary,
    ModeType,
    InputGroundtruthCreate,
)
from ada_backend.schemas.dataset_schema import (
    DatasetCreateList,
    DatasetResponse,
    DatasetDeleteList,
    DatasetListResponse,
)
from ada_backend.services.agent_runner_service import run_agent
from ada_backend.database.models import CallType
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.services.metrics.utils import query_conversation_messages

LOGGER = logging.getLogger(__name__)


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

        try:
            env_relationship = get_env_relationship_by_graph_runner_id(
                session=session, graph_runner_id=run_request.graph_runner_id
            )
            environment = env_relationship.environment
        except ValueError as e:
            raise ValueError(f"Graph runner {run_request.graph_runner_id} not found or not bound to project") from e
        for input_entry in input_entries:
            try:
                # JSONB column should return dict, but handle both cases for safety
                input_data = (
                    input_entry.input if isinstance(input_entry.input, dict) else json.loads(input_entry.input)
                )

                chat_response = await run_agent(
                    session=session,
                    project_id=project_id,
                    graph_runner_id=run_request.graph_runner_id,
                    input_data=input_data,
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
                    input=input_data,
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

                # JSONB column should return dict, but handle both cases for safety
                input_data = (
                    input_entry.input if isinstance(input_entry.input, dict) else json.loads(input_entry.input)
                )

                result = QARunResult(
                    input_id=input_entry.id,
                    input=input_data,
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
        created_inputs_groundtruths = create_inputs_groundtruths(
            session,
            dataset_id,
            inputs_groundtruths_data.inputs_groundtruths,
        )

        LOGGER.info(
            f"Created {len(created_inputs_groundtruths)} input-groundtruth " f"entries for dataset {dataset_id}"
        )

        return InputGroundtruthResponseList(
            inputs_groundtruths=[InputGroundtruthResponse.model_validate(ig) for ig in created_inputs_groundtruths]
        )
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
        updates_data = [(ig.id, ig.input, ig.groundtruth) for ig in inputs_groundtruths_data.inputs_groundtruths]

        updated_inputs_groundtruths = update_inputs_groundtruths(
            session,
            updates_data,
            dataset_id,
        )

        # If any input texts were updated, clear corresponding version outputs across all versions
        input_ids_changed = [ig.id for ig in inputs_groundtruths_data.inputs_groundtruths if ig.input is not None]
        if input_ids_changed:
            clear_version_outputs_for_input_ids(session, input_ids_changed)

        LOGGER.info(
            f"Updated {len(updated_inputs_groundtruths)} input-groundtruth " f"entries for dataset {dataset_id}"
        )

        return InputGroundtruthResponseList(
            inputs_groundtruths=[InputGroundtruthResponse.model_validate(ig) for ig in updated_inputs_groundtruths]
        )
    except Exception as e:
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
    conversation_id: UUID,
    dataset_id: UUID,
    message_index: int,
    mode: ModeType = ModeType.CONVERSATION,
) -> List[InputGroundtruthResponse]:

    input_payload, output_payload = query_conversation_messages(conversation_id)
    input_payload.pop("conversation_id", None)

    messages = input_payload.get("messages", [])

    # Prepare payload based on mode
    if mode == ModeType.CONVERSATION:
        payload = {**input_payload, "messages": messages[: message_index + 1]}
    else:  # ModeType.RAW
        payload = {**input_payload, "messages": [messages[message_index]]}

    # Find groundtruth from next assistant message
    groundtruth_text = None
    next_idx = message_index + 1
    if next_idx < len(messages) and messages[next_idx].get("role") == "assistant":
        groundtruth_text = messages[next_idx].get("content")
    elif output_payload:
        for msg in output_payload.get("messages", []):
            if msg.get("role") == "assistant":
                groundtruth_text = msg.get("content")
                break

    input_entry = InputGroundtruthCreate(input=payload, groundtruth=groundtruth_text)
    input_entries = create_inputs_groundtruths(session, dataset_id, [input_entry])
    return [InputGroundtruthResponse.model_validate(entry) for entry in input_entries]
