import logging
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.repositories.quality_assurance_repository import (
    create_inputs_groundtruths,
    update_inputs_groundtruths,
    delete_inputs_groundtruths,
    get_inputs_groundtruths_with_pagination,
    get_inputs_groundtruths_with_version_outputs_pagination,
    get_inputs_groundtruths_by_ids,
    create_version_output,
    create_datasets,
    update_datasets,
    delete_datasets,
    get_datasets_by_project,
    create_project_versions,
    get_project_versions,
    delete_project_versions,
)
from ada_backend.schemas.quality_assurance_schema import (
    InputGroundtruthResponse,
    InputGroundtruthCreateList,
    InputGroundtruthUpdateList,
    InputGroundtruthDeleteList,
    InputGroundtruthResponseList,
    InputGroundtruthWithVersionResponse,
    QARunRequest,
    QARunResult,
    QARunResponse,
    QARunSummary,
    DatasetCreateList,
    DatasetResponse,
    DatasetUpdateList,
    DatasetDeleteList,
    DatasetListResponse,
    VersionByProjectCreateList,
    VersionByProjectResponse,
    VersionByProjectListResponse,
    VersionDeleteList,
)
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.database.models import EnvType

LOGGER = logging.getLogger(__name__)


# Input Groundtruth services
def get_inputs_groundtruths_by_dataset_service(
    session: Session,
    dataset_id: UUID,
    page: int = 1,
    size: int = 100,
) -> List[InputGroundtruthResponse]:
    """
    Get all input-groundtruth entries for a dataset with pagination.

    Args:
        session (Session): SQLAlchemy session
        dataset_id (UUID): ID of the dataset
        page (int): Page number (1-based)
        size (int): Number of items per page

    Returns:
        List[InputGroundtruthResponse]: List of input-groundtruth entries
    """
    try:
        inputs_groundtruths, _ = get_inputs_groundtruths_with_pagination(session, dataset_id, page, size)

        return [InputGroundtruthResponse.model_validate(ig) for ig in inputs_groundtruths]
    except Exception as e:
        LOGGER.error(f"Error in get_inputs_groundtruths_by_dataset_service: {str(e)}")
        raise ValueError(f"Failed to get input-groundtruth entries: {str(e)}") from e
    finally:
        session.close()


def get_inputs_groundtruths_with_version_outputs_service(
    session: Session,
    dataset_id: UUID,
    version_id: UUID = None,
    page: int = 1,
    size: int = 100,
) -> List[InputGroundtruthWithVersionResponse]:
    """
    Get all input-groundtruth entries for a dataset with version outputs using LEFT JOIN.

    Args:
        session (Session): SQLAlchemy session
        dataset_id (UUID): ID of the dataset
        version_id (UUID, optional): Version ID to filter by
        page (int): Page number (1-based)
        size (int): Number of items per page

    Returns:
        List[InputGroundtruthWithVersionResponse]: List of input-groundtruth entries with version outputs
    """
    try:
        results, _ = get_inputs_groundtruths_with_version_outputs_pagination(
            session, dataset_id, version_id, page, size
        )

        response_list = []
        for input_groundtruth, version_output in results:
            response_data = {
                "input_id": input_groundtruth.id,
                "input": input_groundtruth.input,
                "groundtruth": input_groundtruth.groundtruth,
                "output": version_output.output if version_output else None,
                "version_id": version_output.version_id if version_output else None,
                "version": (
                    version_output.version_by_project.version
                    if version_output and version_output.version_by_project
                    else None
                ),
            }
            response_list.append(InputGroundtruthWithVersionResponse(**response_data))

        return response_list
    except Exception as e:
        LOGGER.error(f"Error in get_inputs_groundtruths_with_version_outputs_service: {str(e)}")
        raise ValueError(f"Failed to get input-groundtruth entries with version outputs: {str(e)}") from e
    finally:
        session.close()


async def run_qa_service(
    session: Session,
    project_id: UUID,
    dataset_id: UUID,
    run_request: QARunRequest,
) -> QARunResponse:
    """
    Run QA process on multiple inputs and store results in VersionOutput table.

    Args:
        session (Session): SQLAlchemy session
        project_id (UUID): ID of the project to run
        dataset_id (UUID): ID of the dataset
        run_request (QARunRequest): Request containing version_id and input_ids

    Returns:
        QARunResponse: Results of the QA run with summary
    """
    try:
        # Get the input-groundtruth entries by their IDs
        input_entries = get_inputs_groundtruths_by_ids(session, run_request.input_ids)

        if not input_entries:
            raise ValueError("No input entries found for the provided input_ids")

        # Verify all inputs belong to the specified dataset
        for entry in input_entries:
            if entry.dataset_id != dataset_id:
                raise ValueError(f"Input {entry.id} does not belong to dataset {dataset_id}")

        # Get the version information
        version_entry = get_project_versions(session, project_id)
        version_entry = next((v for v in version_entry if v.id == run_request.version_id), None)
        if not version_entry:
            raise ValueError(f"Version {run_request.version_id} not found for project {project_id}")

        results = []
        successful_runs = 0
        failed_runs = 0

        # Process each input entry
        for input_entry in input_entries:
            try:
                # Prepare input data for the agent (similar to chat endpoint)
                input_data = {"messages": [{"role": "user", "content": input_entry.input}]}

                # Run the agent using draft environment by default
                chat_response = await run_env_agent(
                    session=session,
                    project_id=project_id,
                    env=EnvType.DRAFT,
                    input_data=input_data,
                )

                # Extract the output message
                output_content = chat_response.message
                if chat_response.error:
                    output_content = f"Error: {chat_response.error}"

                # Store result in VersionOutput table
                _ = create_version_output(
                    session=session,
                    input_id=input_entry.id,
                    output=output_content,
                    version_id=run_request.version_id,
                )

                # TODO : Add a score to determine success or failure
                result = QARunResult(
                    input_id=input_entry.id,
                    input=input_entry.input,
                    groundtruth=input_entry.groundtruth,
                    output=output_content,
                    version_id=run_request.version_id,
                    version=version_entry.version,
                    success=True,  # Everyone passes for now
                    error=None,
                )

                successful_runs += 1

            except Exception as e:
                LOGGER.error(f"Error processing input {input_entry.id}: {str(e)}")

                # Store error result in VersionOutput table
                error_output = f"Error: {str(e)}"
                _ = create_version_output(
                    session=session,
                    input_id=input_entry.id,
                    output=error_output,
                    version_id=run_request.version_id,
                )

                # Prepare error result
                result = QARunResult(
                    input_id=input_entry.id,
                    input=input_entry.input,
                    groundtruth=input_entry.groundtruth,
                    output=error_output,
                    version_id=run_request.version_id,
                    version=version_entry.version,
                    success=False,
                    error=str(e),
                )

                failed_runs += 1

            results.append(result)

        total_processed = len(results)

        # Calculate success rate
        success_rate = (successful_runs / total_processed * 100) if total_processed > 0 else 0.0

        # Create summary
        summary = QARunSummary(
            total=total_processed,
            passed=successful_runs,
            failed=failed_runs,
            success_rate=success_rate,
        )

        LOGGER.info(
            f"QA run completed for project {project_id}, dataset {dataset_id}, version {version_entry.version}"
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
    finally:
        session.close()


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
    finally:
        session.close()


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

        LOGGER.info(
            f"Updated {len(updated_inputs_groundtruths)} input-groundtruth " f"entries for dataset {dataset_id}"
        )

        return InputGroundtruthResponseList(
            inputs_groundtruths=[InputGroundtruthResponse.model_validate(ig) for ig in updated_inputs_groundtruths]
        )
    except Exception as e:
        LOGGER.error(f"Error in update_inputs_groundtruths_service: {str(e)}")
        raise ValueError(f"Failed to update input-groundtruth entries: {str(e)}") from e
    finally:
        session.close()


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
    finally:
        session.close()


# Dataset services
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
    finally:
        session.close()


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
            datasets_data.datasets,
        )

        LOGGER.info(f"Created {len(created_datasets)} datasets for project {project_id}")
        return DatasetListResponse(datasets=[DatasetResponse.model_validate(dataset) for dataset in created_datasets])
    except Exception as e:
        LOGGER.error(f"Error in create_datasets_service: {str(e)}")
        raise ValueError(f"Failed to create datasets: {str(e)}") from e
    finally:
        session.close()


def update_datasets_service(
    session: Session,
    project_id: UUID,
    datasets_data: DatasetUpdateList,
) -> DatasetListResponse:
    """
    Update multiple datasets.

    Args:
        session (Session): SQLAlchemy session
        project_id (UUID): ID of the project
        datasets_data (DatasetUpdateList): Dataset data to update

    Returns:
        DatasetListResponse: The updated datasets
    """
    try:
        # Prepare updates data
        updates_data = [(dataset.id, dataset.dataset_name) for dataset in datasets_data.datasets]

        updated_datasets = update_datasets(
            session,
            updates_data,
            project_id,
        )

        LOGGER.info(f"Updated {len(updated_datasets)} datasets for project {project_id}")
        return DatasetListResponse(datasets=[DatasetResponse.model_validate(dataset) for dataset in updated_datasets])
    except Exception as e:
        LOGGER.error(f"Error in update_datasets_service: {str(e)}")
        raise ValueError(f"Failed to update datasets: {str(e)}") from e
    finally:
        session.close()


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
    finally:
        session.close()


# Project Version services
def get_project_versions_service(
    session: Session,
    project_id: UUID,
) -> List[VersionByProjectResponse]:
    """
    Get all versions for a project.

    Args:
        session (Session): SQLAlchemy session
        project_id (UUID): ID of the project

    Returns:
        List[VersionByProjectResponse]: List of project versions
    """
    try:
        versions = get_project_versions(session, project_id)
        return [VersionByProjectResponse.model_validate(version) for version in versions]
    except Exception as e:
        LOGGER.error(f"Error in get_project_versions_service: {str(e)}")
        raise ValueError(f"Failed to get project versions: {str(e)}") from e
    finally:
        session.close()


def create_project_versions_service(
    session: Session,
    project_id: UUID,
    versions_data: VersionByProjectCreateList,
) -> VersionByProjectListResponse:
    """
    Create project versions.

    Args:
        session (Session): SQLAlchemy session
        project_id (UUID): ID of the project
        versions_data (VersionByProjectCreateList): Version data to create

    Returns:
        VersionByProjectListResponse: The created project versions
    """
    try:
        created_versions = create_project_versions(
            session,
            project_id,
            versions_data.versions,
        )

        LOGGER.info(f"Created {len(created_versions)} versions for project {project_id}")
        return VersionByProjectListResponse(
            versions=[VersionByProjectResponse.model_validate(version) for version in created_versions]
        )
    except Exception as e:
        LOGGER.error(f"Error in create_project_versions_service: {str(e)}")
        raise ValueError(f"Failed to create project versions: {str(e)}") from e
    finally:
        session.close()


def delete_project_versions_service(
    session: Session,
    project_id: UUID,
    delete_data: VersionDeleteList,
) -> int:
    """
    Delete multiple project versions.

    Args:
        session (Session): SQLAlchemy session
        project_id (UUID): ID of the project
        delete_data (VersionDeleteList): IDs of versions to delete

    Returns:
        int: Number of deleted versions
    """
    try:
        deleted_count = delete_project_versions(
            session,
            delete_data.version_ids,
            project_id,
        )

        LOGGER.info(f"Deleted {deleted_count} versions for project {project_id}")
        return deleted_count
    except Exception as e:
        LOGGER.error(f"Error in delete_project_versions_service: {str(e)}")
        raise ValueError(f"Failed to delete project versions: {str(e)}") from e
    finally:
        session.close()
