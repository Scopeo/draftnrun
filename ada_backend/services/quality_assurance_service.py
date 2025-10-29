import logging
from typing import Dict, List, Optional
from uuid import UUID
import uuid

from sqlalchemy.orm import Session

from ada_backend.repositories.quality_assurance_repository import (
    create_inputs_groundtruths,
    update_inputs_groundtruths,
    update_output_groundtruth,
    delete_inputs_groundtruths,
    get_inputs_groundtruths_by_ids,
    get_inputs_groundtruths_by_dataset,
    get_inputs_groundtruths_count_by_dataset,
    get_conversations_count_by_dataset,
    get_conversations_with_outputs,
    upsert_version_output,
    create_datasets,
    update_dataset,
    delete_datasets,
    get_datasets_by_project,
    clear_version_outputs_for_input_ids,
    get_outputs_by_graph_runner,
    create_output_groundtruths,
    get_inputs_by_dataset_and_conversation_ids,
)
from ada_backend.schemas.input_groundtruth_schema import (
    InputGroundtruthResponse,
    InputGroundtruthCreateList,
    InputGroundtruthUpdateWithId,
    InputGroundtruthDeleteList,
    InputGroundtruthResponseList,
    Pagination,
    PaginatedInputGroundtruthResponse,
    QARunRequest,
    QARunResult,
    QARunResponse,
    QARunSummary,
    InputGroundtruthCreate,
    OutputGroundtruthResponse,
    OutputGroundtruthResponseList,
    ModeType,
)
from ada_backend.schemas.dataset_schema import (
    DatasetCreateList,
    DatasetResponse,
    DatasetDeleteList,
    DatasetListResponse,
)
from ada_backend.services.agent_runner_service import run_agent
from ada_backend.database.models import CallType, RoleType, InputGroundtruth
from ada_backend.repositories.env_repository import get_env_relationship_by_graph_runner_id
from ada_backend.services.metrics.utils import query_conversation_messages

LOGGER = logging.getLogger(__name__)


def get_inputs_groundtruths_service(
    session: Session,
    dataset_id: UUID,
    page: int = 1,
    page_size: int = 100,
) -> PaginatedInputGroundtruthResponse:
    """Get conversations with their inputs and corresponding output groundtruths.

    Each conversation includes all its inputs ordered by message order, and the output
    groundtruth linked to the last input in the conversation.

    Args:
        session: SQLAlchemy session
        dataset_id: ID of the dataset
        page: Page number (1-based)
        page_size: Number of conversations per page

    Returns:
        Paginated list of conversations with inputs and outputs
    """
    try:
        skip = (page - 1) * page_size
        total_conversations = get_conversations_count_by_dataset(session, dataset_id)
        total_pages = total_conversations // page_size + (1 if total_conversations % page_size > 0 else 0)

        # Get conversations with outputs
        conversations_data = get_conversations_with_outputs(session, dataset_id, skip, page_size)

        # Flatten all inputs and collect all outputs
        all_inputs = []
        all_outputs = []
        for inputs, output in conversations_data:
            all_inputs.extend(inputs)
            if output:
                all_outputs.append(output)

        return PaginatedInputGroundtruthResponse(
            pagination=Pagination(
                page=page,
                size=page_size,
                total_items=total_conversations,
                total_pages=total_pages,
            ),
            inputs_groundtruths=[InputGroundtruthResponse.model_validate(inp) for inp in all_inputs],
            output_groundtruths=[OutputGroundtruthResponse.model_validate(output) for output in all_outputs],
        )
    except Exception as e:
        LOGGER.error(f"Error in get_conversations_with_outputs_service: {str(e)}")
        raise ValueError(f"Failed to get conversations with outputs: {str(e)}") from e


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
        # Resolve the scope of the run: build conversations to run
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

        # Separate entries by mode: row mode (role is None) vs conversation mode (role is not None)
        row_mode_entries = [e for e in input_entries if e.role is None]
        conversation_mode_entries = [e for e in input_entries if e.role is not None]

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

        # Process row mode entries (each independently)
        for entry in row_mode_entries:
            try:
                # Use just the single entry's input as a message
                messages = [{"role": "user", "content": entry.input}]
                input_data = {"messages": messages}

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

                # Store output for this entry
                upsert_version_output(
                    session=session,
                    input_id=entry.id,
                    output=output_content,
                    graph_runner_id=run_request.graph_runner_id,
                )

                result = QARunResult(
                    input_id=entry.id,
                    input=entry.input,
                    groundtruth=None,
                    output=output_content,
                    graph_runner_id=run_request.graph_runner_id,
                    success=True,
                    error=None,
                )

                successful_runs += 1

            except Exception as e:
                LOGGER.error(f"Error processing row mode entry {entry.id}: {str(e)}")

                error_output = f"Error: {str(e)}"
                upsert_version_output(
                    session=session,
                    input_id=entry.id,
                    output=error_output,
                    graph_runner_id=run_request.graph_runner_id,
                )

                result = QARunResult(
                    input_id=entry.id,
                    input=entry.input,
                    groundtruth=None,
                    output=error_output,
                    graph_runner_id=run_request.graph_runner_id,
                    success=False,
                    error=str(e),
                )

                failed_runs += 1

            results.append(result)

        # Process conversation mode entries (group by conversation_id and build full conversations)
        if conversation_mode_entries:
            conversation_ids = list({e.conversation_id for e in conversation_mode_entries})
            conversation_entries = get_inputs_by_dataset_and_conversation_ids(
                session=session,
                dataset_id=dataset_id,
                conversation_ids=conversation_ids,
            )

            # Build mapping conversation_id -> ordered entries
            conv_to_entries: dict[UUID, list[InputGroundtruth]] = {}
            for e in conversation_entries:
                conv_to_entries.setdefault(e.conversation_id, []).append(e)
            for entries in conv_to_entries.values():
                entries.sort(key=lambda x: x.order)

            # Only process conversations that have entries in our selection
            selected_entry_ids = {entry.id for entry in conversation_mode_entries}
            for conv_id, entries in conv_to_entries.items():
                # Check if any entry in this conversation is in our selection
                if not any(entry.id in selected_entry_ids for entry in entries):
                    continue

                try:
                    # Build full conversation as messages
                    messages = [
                        {
                            "role": (
                                msg.role.value
                                if msg.role and hasattr(msg.role, "value")
                                else (str(msg.role) if msg.role else "user")
                            ),
                            "content": msg.input,
                        }
                        for msg in entries
                    ]
                    input_data = {"messages": messages}

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

                    # Store output for the last message of the conversation
                    last_entry = entries[-1]
                    upsert_version_output(
                        session=session,
                        input_id=last_entry.id,
                        output=output_content,
                        graph_runner_id=run_request.graph_runner_id,
                    )

                    result = QARunResult(
                        input_id=last_entry.id,
                        input=last_entry.input,
                        groundtruth=None,
                        output=output_content,
                        graph_runner_id=run_request.graph_runner_id,
                        success=True,
                        error=None,
                    )

                    successful_runs += 1

                except Exception as e:
                    LOGGER.error(f"Error processing conversation {conv_id}: {str(e)}")

                    error_output = f"Error: {str(e)}"
                    last_entry = entries[-1]
                    upsert_version_output(
                        session=session,
                        input_id=last_entry.id,
                        output=error_output,
                        graph_runner_id=run_request.graph_runner_id,
                    )

                    result = QARunResult(
                        input_id=last_entry.id,
                        input=last_entry.input,
                        groundtruth=None,
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
    groundtruth_message: str,
) -> tuple[InputGroundtruthResponseList, OutputGroundtruthResponseList]:

    try:
        created_inputs_groundtruths = create_inputs_groundtruths(
            session,
            dataset_id,
            inputs_groundtruths_data.inputs_groundtruths,
        )
        created_output_groundtruth = create_output_groundtruths(
            session,
            groundtruth_message,
            created_inputs_groundtruths[-1].id,
        )
        LOGGER.info(
            f"Created {len(created_inputs_groundtruths)} input-groundtruth entries "
            f"and 1 output-groundtruth for dataset {dataset_id}"
        )
        return (
            InputGroundtruthResponseList(
                inputs_groundtruths=[InputGroundtruthResponse.model_validate(ig) for ig in created_inputs_groundtruths]
            ),
            OutputGroundtruthResponseList(
                output_groundtruths=[OutputGroundtruthResponse.model_validate(created_output_groundtruth)]
            ),
        )
    except Exception as e:
        LOGGER.error(f"Error in create_inputs_groundtruths_service: {str(e)}")
        raise ValueError(f"Failed to create input-groundtruth entries: {str(e)}") from e


def update_inputs_service(
    session: Session,
    dataset_id: UUID,
    inputs_groundtruths_data: Optional[list[InputGroundtruthUpdateWithId]] = None,
) -> Optional[list[InputGroundtruthResponse]]:
    try:
        if not inputs_groundtruths_data:
            return None
        updated_inputs_groundtruths = []
        for input_groundtruth in inputs_groundtruths_data:
            updated_inputs_groundtruths.extend(
                update_inputs_groundtruths(
                    session,
                    dataset_id,
                    input_id=input_groundtruth.id,
                    input_text=input_groundtruth.input,
                    role=input_groundtruth.role,
                    order=input_groundtruth.order,
                )
            )
        # If any input texts were updated, clear corresponding version outputs across all versions
        input_ids_changed = [ig.id for ig in updated_inputs_groundtruths if ig.input is not None]
        if input_ids_changed:
            clear_version_outputs_for_input_ids(session=session, input_ids=input_ids_changed)

        LOGGER.info(
            f"Updated {len(updated_inputs_groundtruths)} input-groundtruth " f"entries for dataset {dataset_id}"
        )

        return [InputGroundtruthResponse.model_validate(ig) for ig in updated_inputs_groundtruths]
    except Exception as e:
        LOGGER.error(f"Error in update_inputs_service: {str(e)}")
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

    input_messages, output_messages = query_conversation_messages(conversation_id)

    if not input_messages and not output_messages:
        raise ValueError(f"No spans found for conversation_id {conversation_id}")

    if mode == ModeType.CONVERSATION:
        input_messages = input_messages[: message_index + 1]
        input_entries_data = []
        order = 0
        test_case_id = uuid.uuid4()
        for message in input_messages:
            input_entry = InputGroundtruthCreate(
                conversation_id=test_case_id,
                input=message["content"],
                role=RoleType(message["role"]),
                order=order,
            )
            input_entries_data.append(input_entry)
            order += 1
        input_entries = create_inputs_groundtruths(
            session,
            dataset_id,
            input_entries_data,
        )
        return [InputGroundtruthResponse.model_validate(entry) for entry in input_entries]

    elif mode == ModeType.ROW:
        input_entry = InputGroundtruthCreate(
            conversation_id=uuid.uuid4(),
            input=input_messages[message_index]["content"],
            role=None,
            order=0,
        )
        input_entries = create_inputs_groundtruths(
            session,
            dataset_id,
            [input_entry],
        )
        return [InputGroundtruthResponse.model_validate(entry) for entry in input_entries]


def update_output_groundtruth_service(
    session: Session,
    output_id: Optional[UUID],
    message_id: Optional[UUID],
    output_message: Optional[str],
) -> Optional[OutputGroundtruthResponse]:

    if not output_id and not output_message and not message_id:
        return None

    return update_output_groundtruth(
        session,
        output_id=output_id,
        message_id=message_id,
        output_message=output_message,
    )
